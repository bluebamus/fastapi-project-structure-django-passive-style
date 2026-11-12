"""MySQL 드라이버 오류 코드가 ``convert_db_error`` 를 거쳐 기대한 앱 예외(HTTP 상태)가 된다.

SQLite 판은 ``sqlite_errorname`` 경로를 탄다 — ``_MYSQL_INTEGRITY_KINDS``(1062·1048) 경로는 실제
MySQL 이 숫자 코드를 줄 때만 지나간다.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Numeric, bindparam, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db.session import Base
from app.core.exception import DuplicateException, ValidationException
from app.core.models.types import UTCDateTime
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import SalesReportRawRepository

_INSERT = text(
    """
    INSERT INTO sales_orders
        (id, order_no, customer, total_amount, status, ordered_at, created_at, updated_at)
    VALUES (:id, :order_no, :customer, :total_amount, 'paid', :now, :now, :now)
    """
).bindparams(bindparam("total_amount", type_=Numeric(12, 2)), bindparam("now", type_=UTCDateTime()))


@pytest.fixture
async def repository(mysql_engine: AsyncEngine) -> AsyncIterator[SalesReportRawRepository]:
    async with mysql_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
    session: AsyncSession
    async with async_sessionmaker(mysql_engine)() as session:
        yield SalesReportRawRepository(session)


def _row(order_no: str, customer: str | None = "c") -> dict[str, object]:
    return {
        "id": str(uuid.uuid4()),
        "order_no": order_no,
        "customer": customer,
        "total_amount": 1,
        "now": datetime(2026, 1, 1, tzinfo=UTC),
    }


async def test_duplicate_key_1062_becomes_409(repository: SalesReportRawRepository):
    await repository.execute(_INSERT, _row("DUP-1"), query_name="sales_order.insert")

    with pytest.raises(DuplicateException) as excinfo:
        await repository.execute(_INSERT, _row("DUP-1"), query_name="sales_order.insert")

    assert excinfo.value.status_code == 409
    assert excinfo.value.__cause__ is None and excinfo.value.__suppress_context__


async def test_explicit_null_1048_becomes_422(repository: SalesReportRawRepository):
    with pytest.raises(ValidationException) as excinfo:
        await repository.execute(_INSERT, _row("NULL-1", None), query_name="sales_order.insert")

    assert excinfo.value.status_code == 422
