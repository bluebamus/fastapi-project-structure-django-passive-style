"""Raw 쓰기 workflow 검증 (SCN-RAW-002).

`sales_orders` 에 대한 Raw DML 은 **공개 API 가 아니다** — 리포트 기능은 조회 전용이고,
원본 주문은 다른 시스템이 넣는다. 그래도 Raw 쓰기 경로는 검증해야 한다. 검증하지
않으면 나중에 누군가 Raw DML 을 붙일 때 트랜잭션 규칙이 지켜지는지 아무도 모른다.

그래서 fixture 수준에서 같은 계약을 확인한다.

* ``execute`` 는 영향 행 수를 돌려주고 **커밋하지 않는다**
* 커밋은 호출자가 한 번 한다
* read-only 세션에서는 **실행 전에** 거부된다

Raw UPDATE 는 ``UpdatedAtMixin.onupdate`` 를 발동시키지 않는다는 것도 여기서 고정한다 —
그 동작을 모르고 Raw 로 갱신하면 ``updated_at`` 이 과거에 멈춘 채로 남는다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import DateTime, Numeric, String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import ReadOnlyRoutingError, mark_read_only
from app.core.db.session import Base
from app.core.exception import DuplicateException
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)

QUERY_INSERT = "sales_order.insert"
QUERY_MARK_PAID = "sales_order.mark_paid"
QUERY_COUNT = "sales_order.count"

# ``text()`` 에는 타입 정보가 없다. 그래서 bind 값이 **드라이버로 그대로** 간다 —
# SQLite 는 ``Decimal`` 을, 일부 드라이버는 tz-aware ``datetime`` 을 받지 못한다.
# ORM 경로에서 이 문제가 안 보이는 것은 컬럼 타입이 어댑터를 붙여주기 때문이다.
#
# Raw 에서는 ``bindparams()`` 로 타입을 **명시**한다. 방언별로 SQL 을 갈아끼우는
# 것이 아니라 같은 SQL 에 타입만 알려주는 것이므로, MySQL·SQLite 양쪽에서 그대로 돈다.
_INSERT = text(
    """
    INSERT INTO sales_orders
        (id, order_no, customer, total_amount, status, ordered_at, created_at, updated_at)
    VALUES
        (:id, :order_no, :customer, :total_amount, :status, :ordered_at, :now, :now)
    """
).bindparams(
    bindparam("total_amount", type_=Numeric(12, 2)),
    bindparam("ordered_at", type_=DateTime(timezone=True)),
    bindparam("now", type_=DateTime(timezone=True)),
    bindparam("id", type_=String(36)),
)

#: Raw UPDATE 는 ORM 의 ``onupdate`` 를 타지 않는다 — ``updated_at`` 을 직접 쓴다.
_MARK_PAID = text(
    "UPDATE sales_orders SET status = :status, updated_at = :now WHERE order_no = :order_no"
).bindparams(bindparam("now", type_=DateTime(timezone=True)))

_COUNT_PAID = text("SELECT COUNT(*) FROM sales_orders WHERE status = :status")


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as opened:
        yield opened
    await engine.dispose()


@pytest.fixture
def repo(session: AsyncSession) -> SalesReportRawRepository:
    return SalesReportRawRepository(session)


def _params(order_no: str, *, status: str = "pending") -> dict[str, object]:
    now = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
    return {
        "id": f"id-{order_no}",
        "order_no": order_no,
        "customer": "고객",
        "total_amount": Decimal("1500.00"),
        "status": status,
        "ordered_at": now,
        "now": now,
    }


# =============================================================================
# 영향 행 수와 커밋 경계
# =============================================================================
async def test_insert_reports_the_affected_row_count(repo: SalesReportRawRepository):
    affected = await repo.execute(_INSERT, _params("ORD-100"), query_name=QUERY_INSERT)

    assert affected == 1


async def test_update_reports_the_affected_row_count(repo: SalesReportRawRepository):
    await repo.execute(_INSERT, _params("ORD-101"), query_name=QUERY_INSERT)

    affected = await repo.execute(
        _MARK_PAID,
        {"order_no": "ORD-101", "status": "paid", "now": datetime(2026, 8, 2, tzinfo=UTC)},
        query_name=QUERY_MARK_PAID,
    )

    assert affected == 1


async def test_update_of_a_missing_row_affects_nothing(repo: SalesReportRawRepository):
    affected = await repo.execute(
        _MARK_PAID,
        {"order_no": "없는-주문", "status": "paid", "now": datetime(2026, 8, 2, tzinfo=UTC)},
        query_name=QUERY_MARK_PAID,
    )

    assert affected == 0


async def test_raw_dml_does_not_commit(repo: SalesReportRawRepository, session: AsyncSession):
    """Repository 가 커밋하면 View 의 트랜잭션 경계가 의미를 잃는다."""
    await repo.execute(_INSERT, _params("ORD-102", status="paid"), query_name=QUERY_INSERT)
    await session.rollback()

    remaining = await repo.fetch_scalar(_COUNT_PAID, {"status": "paid"}, query_name=QUERY_COUNT)
    assert remaining == 0, "execute 가 커밋했다 — rollback 이 되돌리지 못했다"


async def test_caller_commits_once_and_the_row_survives(
    repo: SalesReportRawRepository, session: AsyncSession
):
    await repo.execute(_INSERT, _params("ORD-103", status="paid"), query_name=QUERY_INSERT)
    await session.commit()
    await session.rollback()  # 커밋 이후의 rollback 은 아무것도 되돌리지 않는다

    assert await repo.fetch_scalar(_COUNT_PAID, {"status": "paid"}, query_name=QUERY_COUNT) == 1


# =============================================================================
# 실패 경로
# =============================================================================
async def test_duplicate_order_no_becomes_a_conflict(repo: SalesReportRawRepository):
    await repo.execute(_INSERT, _params("ORD-104"), query_name=QUERY_INSERT)

    with pytest.raises(DuplicateException) as caught:
        await repo.execute(_INSERT, {**_params("ORD-104"), "id": "id-dup"}, query_name=QUERY_INSERT)

    assert "ORD-104" not in str(caught.value.detail), "예외 payload 에 bind 값이 실렸다"


# =============================================================================
# read-only 차단
# =============================================================================
async def test_raw_dml_is_refused_on_a_read_only_session(session: AsyncSession):
    """조회 전용 Dependency 로 들어온 세션에서는 Raw 쓰기가 실행되지 않는다."""
    mark_read_only(session)
    repo = SalesReportRawRepository(session)

    with pytest.raises(ReadOnlyRoutingError):
        await repo.execute(_INSERT, _params("ORD-105"), query_name=QUERY_INSERT)


async def test_report_query_still_works_on_a_read_only_session(session: AsyncSession):
    """과차단도 결함이다 — 리포트 조회 자체는 read-only 세션에서 돌아야 한다."""
    mark_read_only(session)
    repo = SalesReportRawRepository(session)

    rows = await repo.daily_sales(
        start_at=datetime(2026, 8, 1).date(), end_exclusive=datetime(2026, 8, 4).date()
    )

    assert list(rows) == []


# =============================================================================
# Raw 갱신과 updated_at
# =============================================================================
async def test_raw_update_must_write_updated_at_itself(
    repo: SalesReportRawRepository, session: AsyncSession
):
    """``onupdate`` 는 ORM 이 UPDATE 를 낼 때만 동작한다.

    Raw UPDATE 에서 ``updated_at`` 을 빼면 값이 과거에 멈춘다. 이 SQL 은 명시적으로
    쓰므로 갱신되고, 그 사실을 여기서 고정한다 — 다음 사람이 컬럼을 지우지 않도록.
    """
    await repo.execute(_INSERT, _params("ORD-106"), query_name=QUERY_INSERT)
    await session.commit()
    later = datetime(2026, 8, 5, 12, 0, tzinfo=UTC)

    await repo.execute(
        _MARK_PAID,
        {"order_no": "ORD-106", "status": "paid", "now": later},
        query_name=QUERY_MARK_PAID,
    )
    await session.commit()

    row = await repo.fetch_one(
        text("SELECT status, updated_at FROM sales_orders WHERE order_no = :order_no"),
        {"order_no": "ORD-106"},
        query_name="sales_order.get",
    )
    assert row is not None
    assert row["status"] == "paid"
    assert str(row["updated_at"]).startswith("2026-08-05"), "Raw UPDATE 가 updated_at 을 남겼다"


def test_sales_order_model_exists_for_schema_ownership():
    """조회를 Raw 로 해도 테이블 소유는 ORM 모델이 선언한다 (SCN-RAW-001)."""
    assert SalesOrder.__tablename__ == "sales_orders"
    assert "sales_orders" in Base.metadata.tables
