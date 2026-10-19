"""Home 기능의 Celery 태스크.

워커는 ``AppConfig.tasks_module``(기본 ``"tasks"``)로 이 module 을 찾아 include 한다
(service-hardening ADR-012). 요청 밖이므로 세션은 ``background_session()`` 이 열고,
서비스 조립은 HTTP 경로와 같은 provider 함수에 맡긴다 — 조립 규칙이 한 곳에 있다.

주기 실행(Celery beat)도 여기서 등록한다. 중앙 Celery 앱은 기능을 import 하지 않고, beat 는
기동 때 워커와 같은 ``include`` 로 이 module 을 불러온 뒤 일정을 읽는다(security-ops-hardening
ADR-003). 앱을 ``INSTALLED_APPS`` 에서 빼면 태스크와 일정이 함께 빠진다.
"""

from typing import Any

from celery.schedules import crontab

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_session
from app.features.home.dependencies.access_log_dependencies import (
    build_user_access_log_service,
)


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict[str, Any]:
        async with background_session() as session:
            stats = await build_user_access_log_service(session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result


#: 접속 로그 보존 삭제 일정 — 매일 03:30. 시각은 Celery ``timezone``(= 설정 ``TIME_ZONE``) 기준이다.
PURGE_SCHEDULE = crontab(hour=3, minute=30)


@celery_app.task(name="home.purge_expired_access_logs")
def purge_expired_access_logs() -> int:
    """``ACCESS_LOG_RETENTION_DAYS`` 보다 오래된 접속 로그를 지우고 지운 행 수를 돌려준다.

    보존 일수가 0 이면 서비스가 DB 에 가지 않고 0 을 돌려준다.
    """

    async def _run() -> int:
        async with background_session() as session:
            return await build_user_access_log_service(session).purge_expired()

    deleted: int = run_async(_run())
    return deleted


celery_app.add_periodic_task(
    PURGE_SCHEDULE,
    purge_expired_access_logs.s(),
    name="home.purge_expired_access_logs",
)
