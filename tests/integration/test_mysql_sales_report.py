"""MySQL 8.4 에서 Raw 집계 SQL 을 실제로 실행한다 (RAW-REP-006 · SCN-RAW-001).

SQLite 단위 테스트는 Base 계약과 컬럼 alias 를 확인하지만 **방언 정확성의 근거가
되지 못한다**(ADR-004). 두 DB 는 같은 SQL 에 서로 다른 타입을 돌려준다.

* ``DATE(o.ordered_at)`` → SQLite 는 문자열, MySQL 은 ``date``
* ``SUM(total_amount)`` → SQLite 는 float, MySQL 은 ``Decimal``

float 로 돌아오는 합계는 돈 계산에서 조용히 틀어진다. 그래서 여기서는 **타입까지**
본다. Pydantic 이 둘 다 받아준다는 사실이 "MySQL 에서 맞다"를 뜻하지는 않는다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import DateTime, Numeric, String, bindparam, text

from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import DailySalesItem

pytestmark = pytest.mark.mysql

# 원본 주문을 Raw 로 심는다 — ORM 을 거치지 않아야 이 테이블이 Raw 경로만으로도
# 다뤄지는지 확인된다. ``text()`` 에는 타입 정보가 없으므로 명시한다.
_INSERT = text(
    """
    INSERT INTO sales_orders
        (id, order_no, customer, total_amount, status, ordered_at, created_at, updated_at)
    VALUES
        (:id, :order_no, :customer, :total_amount, :status, :ordered_at, :now, :now)
    """
).bindparams(
    bindparam("id", type_=String(36)),
    bindparam("total_amount", type_=Numeric(12, 2)),
    bindparam("ordered_at", type_=DateTime(timezone=True)),
    bindparam("now", type_=DateTime(timezone=True)),
)

_SEED = [
    ("ORD-M1", 1, "1000.00", "paid"),
    ("ORD-M2", 1, "2500.50", "paid"),
    ("ORD-M3", 2, "300.25", "paid"),
    ("ORD-M4", 3, "999.00", "cancelled"),
]


async def _seed(session) -> None:
    now = datetime(2026, 8, 1, tzinfo=UTC)
    repo = SalesReportRawRepository(session)
    for order_no, day, amount, status in _SEED:
        await repo.execute(
            _INSERT,
            {
                "id": f"id-{order_no}",
                "order_no": order_no,
                "customer": "고객",
                "total_amount": Decimal(amount),
                "status": status,
                "ordered_at": datetime(2026, 8, day, 10, 30, tzinfo=UTC),
                "now": now,
            },
            query_name="sales_order.insert",
        )
    await session.commit()


@pytest.mark.asyncio
async def test_daily_sales_returns_mysql_native_types(mysql_session_maker):
    """MySQL 이 돌려주는 타입을 그대로 확인한다 — 여기가 SQLite 와 갈리는 지점이다."""
    async with mysql_session_maker() as session:
        await _seed(session)
        rows = await SalesReportRawRepository(session).daily_sales(
            start_at=datetime(2026, 8, 1).date(), end_exclusive=datetime(2026, 8, 4).date()
        )

    assert [str(row["sales_date"]) for row in rows] == ["2026-08-01", "2026-08-02"]
    first = rows[0]
    assert isinstance(first["gross_amount"], Decimal), (
        f"합계가 {type(first['gross_amount']).__name__} 로 왔다 — 돈을 float 으로 다루면 "
        "반올림 오차가 누적된다"
    )
    assert first["gross_amount"] == Decimal("3500.50")
    assert first["order_count"] == 2


@pytest.mark.asyncio
async def test_cancelled_orders_are_excluded_on_mysql(mysql_session_maker):
    async with mysql_session_maker() as session:
        await _seed(session)
        total = await SalesReportRawRepository(session).order_count(
            start_at=datetime(2026, 8, 1).date(), end_exclusive=datetime(2026, 8, 4).date()
        )

    assert total == 3, "cancelled 주문이 MySQL 집계에 섞였다"


@pytest.mark.asyncio
async def test_rows_validate_against_the_response_dto(mysql_session_maker):
    """MySQL 결과가 DTO 검증을 통과한다 — 컬럼 alias 와 필드가 1:1 이어야 한다."""
    async with mysql_session_maker() as session:
        await _seed(session)
        rows = await SalesReportRawRepository(session).daily_sales(
            start_at=datetime(2026, 8, 1).date(), end_exclusive=datetime(2026, 8, 4).date()
        )

    items = [DailySalesItem.model_validate(dict(row)) for row in rows]

    assert [item.sales_date.isoformat() for item in items] == ["2026-08-01", "2026-08-02"]
    assert sum(item.order_count for item in items) == 3


@pytest.mark.asyncio
async def test_end_bound_is_exclusive_on_mysql(mysql_session_maker):
    """배타 상한이 MySQL 에서도 같은 의미다 — ``DATE_ADD`` 를 쓰지 않는 근거."""
    async with mysql_session_maker() as session:
        await _seed(session)
        rows = await SalesReportRawRepository(session).daily_sales(
            start_at=datetime(2026, 8, 1).date(), end_exclusive=datetime(2026, 8, 2).date()
        )

    assert [str(row["sales_date"]) for row in rows] == ["2026-08-01"]


@pytest.mark.asyncio
async def test_injection_payload_is_bound_on_mysql(mysql_session_maker):
    """주입 문자열이 MySQL 에서도 값으로만 취급된다."""
    async with mysql_session_maker() as session:
        await _seed(session)
        repo = SalesReportRawRepository(session)

        rows = await repo.fetch_all(
            text("SELECT order_no FROM sales_orders WHERE customer = :customer"),
            {"customer": "고객' OR '1'='1"},
            query_name="sales_order.by_customer",
        )

        assert list(rows) == [], "주입 문자열이 조건으로 해석됐다"
        assert await repo.fetch_scalar(
            text("SELECT COUNT(*) FROM sales_orders"), query_name="sales_order.count"
        ) == len(_SEED)
