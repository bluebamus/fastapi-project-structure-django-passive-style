"""MySQL 8.4 시각 정책 — UTC·마이크로초 저장과 지역 영업일 집계 (service-hardening 단계 D).

SQLite 는 시각을 문자열로 저장해 fsp·tz 문제를 보여주지 못한다. 여기서 MySQL 로 본다.

1. 모든 시각 컬럼이 ``DATETIME(6)`` 이고, KST aware 값이 **UTC 벽시계**로 저장되며
   마이크로초까지 왕복한다(ledger F-015 의 시각 부분 · F-017).
2. 리포트의 일자 버킷이 ``CONVERT_TZ`` 로 지역 영업일을 따른다 — 2026-01-01T15:30Z 주문은
   Asia/Seoul 로 1월 2일 00:30 이므로 1월 2일 매출이다.

기존 값의 KST → UTC 변환(Alembic 리비전)은 ``test_mysql_migration_roundtrip.py`` 가 본다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from app.features.catalog.models.models import Product
from app.features.reports.models.models import SalesOrder
from app.features.reports.services.report_service import ReportService
from config import TimezoneSettings

pytestmark = pytest.mark.mysql

KST = ZoneInfo("Asia/Seoul")

#: registry 모델의 시각 컬럼 전부(테이블, 컬럼).
DATETIME_COLUMNS = {
    ("user_access_logs", "created_at"),
    *(
        (table, column)
        for table in ("users", "blog_posts", "replies", "sns_posts", "catalog_products")
        for column in ("created_at", "updated_at")
    ),
    ("sales_orders", "ordered_at"),
    ("sales_orders", "created_at"),
    ("sales_orders", "updated_at"),
}


@pytest.mark.asyncio
async def test_every_datetime_column_has_microsecond_precision(mysql_session_maker):
    async with mysql_session_maker() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT TABLE_NAME, COLUMN_NAME, DATETIME_PRECISION FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND DATA_TYPE = 'datetime'"
                )
            )
        ).all()

    assert {(table, column) for table, column, _ in rows} == DATETIME_COLUMNS
    assert {precision for *_, precision in rows} == {6}, rows


@pytest.mark.asyncio
async def test_kst_value_round_trips_as_utc_with_microseconds(mysql_session_maker):
    written = datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST)
    async with mysql_session_maker() as session:
        session.add(
            Product(
                id="p-time",
                sku="TIME-1",
                name="시각",
                price=Decimal("1.00"),
                stock=1,
                created_at=written,
                updated_at=written,
            )
        )
        await session.commit()

    async with mysql_session_maker() as session:
        stored = await session.scalar(
            text("SELECT created_at FROM catalog_products WHERE id = 'p-time'")
        )
        loaded = await session.scalar(select(Product.created_at).where(Product.id == "p-time"))

    # DB 에는 UTC 벽시계(마이크로초 포함)가, ORM 에는 aware UTC 가 온다.
    assert stored == datetime(2026, 1, 1, 15, 30, 0, 123456)
    assert loaded == written
    assert loaded.tzinfo is UTC
    assert loaded.microsecond == 123456


@pytest.mark.asyncio
async def test_daily_sales_bucket_follows_the_local_business_day(mysql_session_maker):
    async with mysql_session_maker() as session:
        session.add_all(
            [
                SalesOrder(
                    order_no=order_no,
                    customer="고객",
                    total_amount=Decimal("100.00"),
                    status="paid",
                    ordered_at=ordered_at,
                )
                for order_no, ordered_at in (
                    (
                        "ORD-A",
                        datetime(2026, 1, 1, 14, 59, 59, 999999, tzinfo=UTC),
                    ),  # 1/1 23:59 KST
                    ("ORD-B", datetime(2026, 1, 1, 15, 30, tzinfo=UTC)),  # 1/2 00:30 KST
                    ("ORD-C", datetime(2026, 1, 2, 15, 0, tzinfo=UTC)),  # 1/3 00:00 KST
                )
            ]
        )
        await session.commit()

    service_tz = TimezoneSettings(TIME_ZONE="Asia/Seoul")
    async with mysql_session_maker() as session:
        service = ReportService(session, service_tz)
        jan2 = await service.daily_sales_report(
            start_date=date(2026, 1, 2), end_date=date(2026, 1, 2)
        )
        span = await service.daily_sales_report(
            start_date=date(2026, 1, 1), end_date=date(2026, 1, 3)
        )

    assert jan2.order_count == 1
    assert [(item.sales_date, item.order_count) for item in jan2.items] == [(date(2026, 1, 2), 1)]
    assert [(item.sales_date, item.order_count) for item in span.items] == [
        (date(2026, 1, 1), 1),
        (date(2026, 1, 2), 1),
        (date(2026, 1, 3), 1),
    ]
