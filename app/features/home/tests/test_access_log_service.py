"""Home 접속 로그 서비스의 실제 DB 동작 검증 (UnitOfWork 제거 후 세션 기반).

in-memory sqlite 로 service → repository → ORM CRUD 흐름을 검증한다.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog  # noqa: F401  (register table)
from app.features.home.services.user_access_log_service import UserAccessLogService


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_and_list(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {"ip_address": "1.2.3.4", "request_path": "/x", "request_method": "GET"}
    )
    await session.commit()

    logs, total = await service.get_access_logs()
    assert total == 1
    assert logs[0].ip_address == "1.2.3.4"
    assert logs[0].id  # repository auto-assigns UUID


@pytest.mark.asyncio
async def test_stats_counts_device_type(session):
    service = UserAccessLogService(session)
    await service.create_access_log(
        {
            "ip_address": "1.1.1.1",
            "request_path": "/a",
            "request_method": "GET",
            "device_type": "desktop",
        }
    )
    await session.commit()

    stats = await service.get_stats()
    assert stats.total_count == 1
    assert any(d.device_type == "desktop" and d.count == 1 for d in stats.device_types)


@pytest.mark.asyncio
async def test_time_ordered_queries_break_ties_by_id(session):
    """``created_at desc`` 만으로는 같은 시각의 행 순서가 정해지지 않는다(service-hardening F-002).

    동률이면 페이지마다 다른 행이 나와 offset 페이지가 겹치거나 빠진다. ``id desc`` 보조 키로
    순서를 고정한다 — 같은 시각의 행은 id 역순으로 나와야 하고 페이지가 겹치지 않아야 한다.
    """
    from datetime import UTC, datetime

    from app.features.home.repositories.user_access_log_repository import (
        UserAccessLogRepository,
    )

    repo = UserAccessLogRepository(session)
    same = datetime(2026, 10, 12, 1, 2, 3, tzinfo=UTC)
    for log_id in ("log-a", "log-b", "log-c", "log-d"):
        await repo.create(
            {
                "id": log_id,
                "ip_address": "9.9.9.9",
                "user_id": "u1",
                "request_path": "/t",
                "request_method": "GET",
                "created_at": same,
            }
        )
    await session.flush()
    expected = ["log-d", "log-c", "log-b", "log-a"]

    queries = {
        "by_ip": lambda skip, limit: repo.get_by_ip("9.9.9.9", skip=skip, limit=limit),
        "by_user": lambda skip, limit: repo.get_by_user_id("u1", skip=skip, limit=limit),
        "by_range": lambda skip, limit: repo.get_by_date_range(same, same, skip=skip, limit=limit),
    }
    for name, query in queries.items():
        pages = [log.id for skip in (0, 2) for log in await query(skip, 2)]
        assert pages == expected, name

    assert [log.id for log in await repo.get_recent_logs(limit=4)] == expected
