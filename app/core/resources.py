"""애플리케이션 프로세스 수명 자원의 생성·해제 단일 지점 (development-plan §9).

``bootstrap.lifespan`` 은 이 컨텍스트를 열고 yield 하는 **조립만** 담당한다.
자원별 startup/shutdown 코드를 lifespan 에 나열하면 종료 순서가 암묵적이 되고,
startup 중간에 실패했을 때 이미 만든 자원이 새는 경로가 생긴다.

종료 순서 (역순 등록으로 강제한다)::

    1. in-flight background task drain   — DB 를 쓰는 주체를 먼저 멈춘다
    2. DB writer/reader/background engine dispose

``AsyncExitStack`` 은 callback 을 **등록 역순**으로 실행하므로 위 순서의 역순으로
등록한다. 각 cleanup 은 :func:`_run_cleanup` 이 감싸서 실패·timeout 을 로깅만 하고
삼킨다 — 하나가 실패했다고 뒤따르는 cleanup 을 건너뛰면 자원이 새기 때문이다.

logging 은 여기서 다루지 않는다. 이 저장소는 ADR-019(console + RotatingFileHandler)
를 유지하고 queue listener 를 두지 않기로 했다(ADR-003) — 닫을 자원이 없다.

테이블 자동 생성은 파일 존재 여부가 아니라 **App Registry 가 소유한 테이블 수**로
판정한다. 소유 테이블이 0개면 DB 에 접속조차 하지 않는다.

자원 소유권은 FastAPI API 프로세스가 만든 것으로 한정한다. Celery worker 의 event
loop 와 그 루프에 묶인 pool 은 worker 프로세스가 소유하며 여기서 닫지 않는다
(`app/celery/lifecycle.py`).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from app.core.db.session import create_db_tables, dispose_engine, owned_tables
from app.core.middlewares.background_tasks import access_log_tasks
from app.utils.logs import get_logger
from config import app_settings

logger = get_logger("resources")

# 자원별 shutdown 예산. 합이 전체 예산을 넘지 않아야 한다.
BACKGROUND_DRAIN_TIMEOUT_SECONDS = 5.0
DB_DISPOSE_TIMEOUT_SECONDS = 10.0

# drain 예산 중 "완료를 기다리는" 몫. 나머지는 timeout 이후 pending 을 취소하고
# 회수(gather)하는 데 쓴다. 바깥 guard 와 같은 값을 주면 취소 회수 도중 잘려,
# 태스크의 finally(세션 rollback/close)가 실행되지 못한 채 DB dispose 로 넘어간다.
DRAIN_WAIT_RATIO = 0.8


@dataclass(slots=True)
class ApplicationResources:
    """이 프로세스가 실제로 생성한 장기 수명 자원과 startup 판정 결과.

    ``app.state.resources`` 로 참조하며, shutdown 후에는 닫힌 자원을 가리키지
    않도록 ``None`` 으로 되돌린다.
    """

    table_count: int = 0
    tables_created: bool = False


async def _run_cleanup(
    name: str,
    action: Callable[[], Awaitable[None]],
    timeout: float,
) -> None:
    """cleanup 하나를 timeout 안에서 실행하고 실패를 삼킨다.

    예외를 밖으로 던지면 ``AsyncExitStack`` 이 그 예외를 들고 나머지 callback 을
    처리하게 되어 종료 로그가 어지러워지고, 무엇보다 원래의 startup 실패 원인이
    cleanup 실패로 덮인다. 여기서 기록하고 끝낸다.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(timeout):
            await action()
    except TimeoutError:
        logger.error("[shutdown] %s 정리 timeout (%.1fs 초과)", name, timeout)
    except Exception as exc:
        # 예외 **메시지**는 남기지 않는다 — DB 예외의 str() 에는 SQL 과 바인딩
        # 값이 들어 있고 이 로거는 sql_noise 필터를 통과한다 (C-13).
        logger.error("[shutdown] %s 정리 실패: %s", name, type(exc).__name__)
    else:
        elapsed = (time.perf_counter() - started) * 1000
        logger.info("[shutdown] %s 정리 완료 (%.1fms)", name, elapsed)


async def _drain_background_tasks() -> None:
    wait_timeout = BACKGROUND_DRAIN_TIMEOUT_SECONDS * DRAIN_WAIT_RATIO
    await _run_cleanup(
        "background task",
        lambda: access_log_tasks.drain(timeout=wait_timeout),
        BACKGROUND_DRAIN_TIMEOUT_SECONDS,
    )


async def _dispose_db_engines() -> None:
    await _run_cleanup("DB engine", dispose_engine, DB_DISPOSE_TIMEOUT_SECONDS)


async def _prepare_database(resources: ApplicationResources) -> None:
    """registry 를 채우고, 소유 테이블 수를 근거로 자동 생성 여부를 판정한다."""
    from app.core.apps import apps
    from config import INSTALLED_APPS

    # ready() 는 wiring adapter 가 별도로 실행한다. 여기서는 모델만 확보한다.
    apps.populate(INSTALLED_APPS, run_ready=False)
    resources.table_count = len(owned_tables())
    logger.info("[startup] registry 소유 테이블 %d개", resources.table_count)

    if resources.table_count == 0:
        logger.info("[startup] 소유 테이블이 없어 DB 연결과 테이블 생성을 건너뛴다")
        return

    if not app_settings.DEBUG:
        logger.info("[startup] 테이블 자동 생성 건너뜀 (운영 정책 — Alembic 사용)")
        return

    # registry 는 위에서 이미 채웠다. 다시 populate 하면 같은 startup 에서
    # discovery 가 두 번 도는 셈이라 로그와 소요 시간이 어긋난다.
    await create_db_tables(populate=False)
    resources.tables_created = True
    logger.info("[startup] 테이블 자동 생성 완료 (개발 정책)")


@asynccontextmanager
async def manage_application_resources(
    app: FastAPI,
) -> AsyncIterator[ApplicationResources]:
    """프로세스 수명 자원을 생성하고, 정상·실패 종료 모두에서 해제한다."""
    resources = ApplicationResources()
    app.state.resources = resources
    started = time.perf_counter()
    logger.info("[startup] 애플리케이션 자원 초기화 시작 (DEBUG=%s)", app_settings.DEBUG)

    try:
        async with AsyncExitStack() as cleanup:
            # 등록 역순으로 실행된다 → 원하는 종료 순서의 역순으로 등록한다.
            # DB 를 쓰는 주체(background task)를 먼저 멈춘 뒤 engine 을 닫아야
            # 이미 닫힌 pool 을 만지는 태스크가 남지 않는다.
            cleanup.push_async_callback(_dispose_db_engines)  # 2번째로 실행
            cleanup.push_async_callback(_drain_background_tasks)  # 1번째로 실행

            await _prepare_database(resources)

            elapsed = (time.perf_counter() - started) * 1000
            logger.info("[startup] 자원 초기화 완료 (%.1fms)", elapsed)
            yield resources
            logger.info("[shutdown] 애플리케이션 자원 해제 시작")
    finally:
        # 닫힌 자원을 다음 lifespan/테스트가 재사용하지 않도록 참조도 지운다.
        app.state.resources = None
        logger.info("[shutdown] 애플리케이션 자원 해제 완료")
