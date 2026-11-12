"""``UTCDateTime`` 이 실제 MySQL ``DATETIME(6)`` 에서 마이크로초까지 왕복하고 UTC 로 돌아온다.

SQLite 는 시각을 문자열로 저장해 fsp 절삭·tz 무시가 드러나지 않는다 — 그건 MySQL 에서만 본다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.db.session import Base
from app.features.reports.models.models import SalesOrder

KST = ZoneInfo("Asia/Seoul")


async def test_kst_value_is_stored_as_utc_wall_clock_and_read_back_as_utc(
    mysql_engine: AsyncEngine,
):
    async with mysql_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
    maker = async_sessionmaker(mysql_engine, expire_on_commit=False)
    written = datetime(2026, 3, 2, 0, 30, 15, 123456, tzinfo=KST)

    async with maker() as session:
        session.add(
            SalesOrder(
                order_no="UTC-1", customer="c", total_amount=Decimal("1.00"), ordered_at=written
            )
        )
        await session.commit()

    async with maker() as session:
        loaded = (await session.execute(select(SalesOrder.ordered_at))).scalar_one()
        raw = (await session.execute(text("SELECT ordered_at FROM sales_orders"))).scalar_one()

    assert loaded == written and loaded.tzinfo is UTC
    assert loaded.microsecond == 123456  # DATETIME(6) — 잘리지 않는다
    # 저장된 벽시계는 KST 가 아니라 UTC 다(타입을 거치지 않은 Raw 값으로 확인).
    assert raw == datetime(2026, 3, 1, 15, 30, 15, 123456)
