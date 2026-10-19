"""접속 로그 보존 삭제 — 경계·배치·0·설정·beat 일정·조립 (security-ops-hardening ADR-002·ADR-003).

실제 SQLite(in-memory)로 service → repository → DELETE 를 돈다. 기준 시각은 ``now=`` 로 주입한다.
MySQL 방언의 같은 쿼리는 ``tests/integration/test_mysql_access_log_retention.py`` 가 본다.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from celery.schedules import crontab
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home import tasks
from app.features.home.dependencies import access_log_dependencies
from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import (
    PURGE_BATCH_SIZE,
    UserAccessLogService,
)
from config import MiddlewareSettings

NOW = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[UserAccessLog.__table__])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        yield s
    await engine.dispose()


async def _seed(session, *created_at: datetime) -> None:
    session.add_all(
        UserAccessLog(
            ip_address="10.0.0.1", request_path=f"/p{i}", request_method="GET", created_at=at
        )
        for i, at in enumerate(created_at)
    )
    await session.commit()


async def _paths(session) -> set[str]:
    return set((await session.execute(select(UserAccessLog.request_path))).scalars())


async def test_only_rows_older_than_the_retention_boundary_are_deleted(session):
    cutoff = NOW - timedelta(days=30)
    await _seed(
        session,
        cutoff - timedelta(seconds=1),  # /p0 — 지운다
        cutoff - timedelta(microseconds=1),  # /p1 — 지운다
        cutoff,  # /p2 — 정확히 N일 전: 남는다
        cutoff + timedelta(seconds=1),  # /p3 — 남는다
    )

    deleted = await UserAccessLogService(session, retention_days=30).purge_expired(now=NOW)

    assert deleted == 2
    assert await _paths(session) == {"/p2", "/p3"}


@pytest.mark.parametrize(("rows", "calls"), [(7, 3), (6, 3), (2, 1)])
async def test_deletes_in_batches_and_commits_each_batch(session, rows, calls):
    await _seed(session, *(NOW - timedelta(days=40, minutes=i) for i in range(rows)))
    await _seed(session, NOW)  # 보존 기간 안 — 남는다
    service = UserAccessLogService(session, retention_days=30)
    batches: list[int] = []
    commits: list[int] = []
    original_delete = service.repository.delete_created_before
    original_commit = service.commit

    async def spy_delete(cutoff, limit):
        batches.append(await original_delete(cutoff, limit))
        return batches[-1]

    async def spy_commit():
        commits.append(len(batches))
        await original_commit()

    service.repository.delete_created_before = spy_delete  # type: ignore[method-assign]
    service.commit = spy_commit  # type: ignore[method-assign]

    deleted = await service.purge_expired(now=NOW, batch_size=3)

    assert deleted == rows
    assert len(batches) == calls and all(b <= 3 for b in batches), batches
    assert commits == list(range(1, calls + 1)), "배치마다 커밋하지 않았다"
    assert await session.scalar(select(func.count()).select_from(UserAccessLog)) == 1


async def test_zero_retention_deletes_nothing_and_does_not_query(session):
    await _seed(session, NOW - timedelta(days=4000))
    service = UserAccessLogService(session, retention_days=0)

    async def forbidden(*_):  # pragma: no cover - 불리면 실패
        raise AssertionError("보존 0 인데 삭제 쿼리를 냈다")

    service.repository.delete_created_before = forbidden  # type: ignore[method-assign]

    assert await service.purge_expired(now=NOW) == 0
    assert await _paths(session) == {"/p0"}


def test_default_batch_size_is_bounded():
    assert PURGE_BATCH_SIZE == 5_000


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def test_retention_setting_defaults_to_one_year(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ACCESS_LOG_RETENTION_DAYS", raising=False)

    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 365


def test_retention_setting_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "0")

    assert MiddlewareSettings(_env_file=None).ACCESS_LOG_RETENTION_DAYS == 0


def test_negative_retention_is_rejected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ACCESS_LOG_RETENTION_DAYS", "-1")

    with pytest.raises(ValidationError, match="ACCESS_LOG_RETENTION_DAYS"):
        MiddlewareSettings(_env_file=None)


# ---------------------------------------------------------------------------
# 조립 · 일정
# ---------------------------------------------------------------------------
def test_provider_passes_the_configured_retention(monkeypatch: pytest.MonkeyPatch):
    from config import middleware_settings

    monkeypatch.setattr(middleware_settings, "ACCESS_LOG_RETENTION_DAYS", 42)

    service = access_log_dependencies.build_user_access_log_service(object())  # type: ignore[arg-type]

    assert service.retention_days == 42


def test_purge_task_is_scheduled_daily_at_0330_local_time():
    from app.celery.app import celery_app
    from config import timezone_settings

    entry = celery_app.conf.beat_schedule["home.purge_expired_access_logs"]

    assert entry["task"] == tasks.purge_expired_access_logs.name == "home.purge_expired_access_logs"
    assert entry["schedule"] == crontab(hour=3, minute=30)
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE
    assert "home.purge_expired_access_logs" in celery_app.tasks


def test_purge_task_builds_the_service_through_the_provider(monkeypatch: pytest.MonkeyPatch):
    session = object()
    seen: list[object] = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class FakeService:
        async def purge_expired(self) -> int:
            return 11

    def fake_build(received: object) -> FakeService:
        seen.append(received)
        return FakeService()

    monkeypatch.setattr(tasks, "background_session", fake_background_session)
    monkeypatch.setattr(tasks, "build_user_access_log_service", fake_build)
    monkeypatch.setattr(tasks, "run_async", asyncio.run)

    assert tasks.purge_expired_access_logs() == 11
    assert seen == [session]
