"""매출 리포트 Raw SQL 의 **MySQL 전용 분기**(``CONVERT_TZ`` 일자 버킷) 결과값.

SQLite 단위 테스트는 ``DATE(col, '+540 minutes')`` 분기를 탄다. MySQL 분기의 SQL·오프셋 문자열
(``mysql_offset``)·반환 타입(``date``·``Decimal``)은 여기서만 검증된다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.db.session import Base
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository

KST_OFFSET = timedelta(hours=9)


def _order(order_no: str, ordered_at: datetime, amount: str, status: str = "paid") -> SalesOrder:
    return SalesOrder(
        order_no=order_no,
        customer="c",
        total_amount=Decimal(amount),
        status=status,
        ordered_at=ordered_at,
    )


@pytest.fixture
async def repository(mysql_engine: AsyncEngine) -> AsyncIterator[SalesReportRawRepository]:
    async with mysql_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(
            [
                # 2026-03-01 23:59:59.999999 KST — 3월 1일 버킷
                _order("A", datetime(2026, 3, 1, 14, 59, 59, 999999, tzinfo=UTC), "10.50"),
                # 2026-03-02 00:00 KST — UTC 로는 3월 1일이지만 3월 2일 버킷
                _order("B", datetime(2026, 3, 1, 15, 0, tzinfo=UTC), "20.25"),
                _order("C", datetime(2026, 3, 2, 3, 0, tzinfo=UTC), "1.00"),
                _order("X", datetime(2026, 3, 1, 16, 0, tzinfo=UTC), "99.00", status="cancelled"),
                # 기간 밖(2026-03-03 00:00 KST)
                _order("Z", datetime(2026, 3, 2, 15, 0, tzinfo=UTC), "50.00"),
            ]
        )
        await session.commit()
        yield SalesReportRawRepository(session)


async def test_daily_sales_buckets_by_local_day_with_convert_tz(
    repository: SalesReportRawRepository,
):
    rows = await repository.daily_sales(
        start_at=datetime(2026, 2, 28, 15, 0, tzinfo=UTC),  # 03-01 00:00 KST
        end_exclusive=datetime(2026, 3, 2, 15, 0, tzinfo=UTC),  # 03-03 00:00 KST
        utc_offset=KST_OFFSET,
    )

    assert [dict(row) for row in rows] == [
        {"sales_date": date(2026, 3, 1), "order_count": 1, "gross_amount": Decimal("10.50")},
        {"sales_date": date(2026, 3, 2), "order_count": 2, "gross_amount": Decimal("21.25")},
    ]


async def test_daily_sales_negative_half_hour_offset(repository: SalesReportRawRepository):
    """``-03:30`` — 부호·분 단위 오프셋 문자열이 MySQL 에서 그대로 받아들여진다."""
    rows = await repository.daily_sales(
        start_at=datetime(2026, 3, 1, 3, 30, tzinfo=UTC),  # 03-01 00:00 (-03:30)
        end_exclusive=datetime(2026, 3, 2, 3, 30, tzinfo=UTC),  # 03-02 00:00 (-03:30)
        utc_offset=-timedelta(hours=3, minutes=30),
    )

    # A(14:59Z)·B(15:00Z) → 03-01 11:29·11:30 지역시각, C(03-02 03:00Z) → 03-01 23:30.
    assert [(row["sales_date"], row["order_count"]) for row in rows] == [(date(2026, 3, 1), 3)]
    assert (
        await repository.order_count(
            start_at=datetime(2026, 3, 1, 3, 30, tzinfo=UTC),
            end_exclusive=datetime(2026, 3, 2, 3, 30, tzinfo=UTC),
        )
        == 3
    )
