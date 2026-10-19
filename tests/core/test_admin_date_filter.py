"""관리 목록 날짜 필터 ``LocalDateFilter`` — 지역 날짜 경계·연산 3종·잘못된 입력 (security-ops-hardening ADR-005).

실제 SQLite 에 ``UTCDateTime`` 컬럼(접속 로그 ``created_at``)을 두고 필터가 만든 질의를 돌린다.
시간대는 Asia/Seoul(UTC+9)로 고정한다 — 2026-10-12 의 지역 0시는 2026-10-11T15:00Z 다.
모든 관리 뷰의 목록에 이 필터를 건 HTTP 확인은 ``tests/core/test_admin_pages.py`` 가 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.admin_filters import LocalDateFilter
from app.core.db.session import Base
from app.features.home.models.models import UserAccessLog
from config import TimezoneSettings

SEOUL = TimezoneSettings(TIME_ZONE="Asia/Seoul")
#: 2026-10-12 지역 0시 = UTC 전날 15시.
MIDNIGHT_12 = datetime(2026, 10, 11, 15, 0, tzinfo=UTC)
MIDNIGHT_13 = MIDNIGHT_12 + timedelta(days=1)

ROWS = {
    "/before-12": MIDNIGHT_12 - timedelta(seconds=1),  # 10-11 23:59:59 KST
    "/start-12": MIDNIGHT_12,  # 10-12 00:00:00 KST
    "/end-12": MIDNIGHT_13 - timedelta(seconds=1),  # 10-12 23:59:59 KST
    "/start-13": MIDNIGHT_13,  # 10-13 00:00:00 KST
}


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[UserAccessLog.__table__])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        s.add_all(
            UserAccessLog(ip_address="1.1.1.1", request_path=p, request_method="GET", created_at=at)
            for p, at in ROWS.items()
        )
        await s.commit()
        yield s
    await engine.dispose()


def _filter() -> LocalDateFilter:
    return LocalDateFilter(UserAccessLog.created_at, timezone=SEOUL)


async def _apply(session, operation: str, value: str) -> set[str]:
    base = select(UserAccessLog.request_path)
    query = await _filter().get_filtered_query(base, operation, value, UserAccessLog)
    return set((await session.execute(query)).scalars())


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("on", {"/start-12", "/end-12"}),
        ("from", {"/start-12", "/end-12", "/start-13"}),
        ("before", {"/before-12"}),
    ],
)
async def test_operations_use_local_midnight_boundaries(session, operation, expected):
    assert await _apply(session, operation, "2026-10-12") == expected


@pytest.mark.parametrize("value", ["2026-13-01", "12/10/2026", "yesterday", "", "2026-10-12T00:00"])
async def test_malformed_dates_leave_the_query_unfiltered(session, value):
    assert await _apply(session, "on", value) == set(ROWS)


async def test_unknown_operation_leaves_the_query_unfiltered(session):
    assert await _apply(session, "greater_than", "2026-10-12") == set(ROWS)


def test_follows_the_sqladmin_operation_filter_protocol():
    f = _filter()

    assert f.has_operator is True
    assert f.parameter_name == "created_at"
    assert [op for op, _ in f.get_operation_options_for_model(UserAccessLog)] == [
        "on",
        "from",
        "before",
    ]
    assert f.template == "sqladmin/filters/local_date_filter.html"


def test_quick_ranges_are_counted_in_local_days():
    class FixedClock(TimezoneSettings):
        def utc_now(self) -> datetime:
            return datetime(2026, 10, 12, 15, 30, tzinfo=UTC)  # 10-13 00:30 KST

    f = LocalDateFilter(UserAccessLog.created_at, timezone=FixedClock(TIME_ZONE="Asia/Seoul"))

    assert f.quick_ranges() == [
        ("오늘", "on", "2026-10-13"),
        ("최근 7일", "from", "2026-10-07"),
        ("최근 30일", "from", "2026-09-14"),
    ]
