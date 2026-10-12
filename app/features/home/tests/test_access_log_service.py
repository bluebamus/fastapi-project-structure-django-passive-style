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


@pytest.mark.asyncio
async def test_long_strings_are_cut_to_the_column_length(session):
    """클라이언트가 정한 긴 헤더·쿠키는 컬럼 길이로 잘려 저장된다(service-hardening F-006).

    SQLite 는 길이를 강제하지 않으므로 저장된 값의 길이로 확인한다. MySQL strict 에서는
    자르지 않으면 1406 으로 INSERT 가 거부돼 기록이 빠진다. 길이는 모델에서 읽는다.
    """
    columns = UserAccessLog.__table__.c
    service = UserAccessLogService(session)
    long_value = "가" * 5000

    created = await service.create_access_log(
        {
            "ip_address": "1.1.1.1",
            "request_path": "/" + long_value,
            "request_method": "GET",
            "forwarded_for": long_value,
            "accept_language": long_value,
            "session_id": long_value,
            "browser_name": long_value,
            "user_agent": long_value,  # Text — 길이 제한 없음
        }
    )
    await session.commit()

    assert len(created.request_path) == columns["request_path"].type.length
    assert len(created.forwarded_for) == columns["forwarded_for"].type.length
    assert len(created.accept_language) == columns["accept_language"].type.length
    assert len(created.session_id) == columns["session_id"].type.length
    assert len(created.browser_name) == columns["browser_name"].type.length
    assert created.user_agent == long_value
