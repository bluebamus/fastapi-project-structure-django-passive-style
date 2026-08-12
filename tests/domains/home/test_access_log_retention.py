"""접속 로그 보존 정책 (계획서 P1-2 — 데이터 최소화의 시간 축).

지운 적이 없으면 IP·사용자 ID 가 묶인 기록이 무한정 쌓인다. 개인정보는 "필요한
기간만" 보관해야 하고, 저장 공간도 계속 늘어난다.

삭제는 Admin 클릭이 아니라 정책이 담당한다 — Admin 의 접속로그 삭제 버튼은
막아뒀다(감사 기록의 무결성). 대신 보존 기간이 지난 것만 반복 실행 가능하게
지운다.
"""

from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import UserAccessLogService
from config import timezone_settings


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def _seed(session, *, days_ago: int, path: str) -> None:
    session.add(
        UserAccessLog(
            ip_address="1.2.3.4",
            request_path=path,
            request_method="GET",
            created_at=timezone_settings.now() - timedelta(days=days_ago),
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_deletes_only_logs_older_than_retention(session):
    await _seed(session, days_ago=100, path="/old")
    await _seed(session, days_ago=10, path="/recent")
    await session.commit()

    deleted = await UserAccessLogService(session).purge_logs_older_than(days=90)
    await session.commit()

    assert deleted == 1
    logs, total = await UserAccessLogService(session).get_access_logs()
    assert total == 1
    assert logs[0].request_path == "/recent"


@pytest.mark.asyncio
async def test_purge_is_repeatable(session):
    """두 번째 실행이 실패하거나 더 지우지 않는다(스케줄러가 반복 호출한다)."""
    await _seed(session, days_ago=100, path="/old")
    await session.commit()

    service = UserAccessLogService(session)
    assert await service.purge_logs_older_than(days=90) == 1
    await session.commit()
    assert await service.purge_logs_older_than(days=90) == 0
    await session.commit()


@pytest.mark.asyncio
async def test_zero_retention_is_rejected(session):
    """0 이하를 허용하면 '보존 안 함' 이 아니라 '전부 삭제' 가 된다 — 사고를 막는다."""
    with pytest.raises(ValueError):
        await UserAccessLogService(session).purge_logs_older_than(days=0)


def test_retention_task_is_registered():
    """스케줄러가 부를 수 있게 Celery 태스크로 노출돼 있어야 한다.

    worker 가 하는 것과 같은 방식(conf.include 로딩)으로 확인한다 — 태스크
    모듈을 직접 import 하면 include 에서 빠져도 통과해 버린다.
    """
    from app.celery.app import celery_app

    celery_app.loader.import_default_modules()

    assert "home.purge_old_access_logs" in celery_app.tasks
