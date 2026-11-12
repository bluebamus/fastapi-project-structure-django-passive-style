"""읽기/쓰기 라우팅이 실제 MySQL 연결에서도 성립한다.

구성: writer = 테스트 DB 의 관리자 연결, reader = **같은 서버**의 ``SELECT`` 전용 사용자 연결.

증명하는 것:
    * 라우팅 세션의 쓰기(flush)는 writer 로, 읽기는 reader 로 간다 — 쓰기가 reader 로 갔다면 MySQL 이
      권한 오류(1142)로 거부했을 것이다.
    * 읽기 전용 세션의 ORM flush·Raw DML 은 **MySQL 에 보내기 전에** ``ReadOnlyRoutingError`` 로 막힌다
      (행 수가 그대로다).
    * reader 자격으로는 실제로 쓸 수 없다(1142) — 위 증명의 전제.

증명하지 못하는 것: 서로 다른 서버 간 복제 지연·replica 장애 전환(같은 서버라 데이터가 즉시 같다),
``read_only``/``super_read_only`` 서버 변수로 막힌 실제 replica 의 동작.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db.errors import driver_error_code
from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    write_intent,
)
from app.core.db.session import Base
from app.features.reports.models.models import SalesOrder

#: ER_TABLEACCESS_DENIED_ERROR — 권한 없는 사용자가 INSERT 할 때.
MYSQL_TABLE_ACCESS_DENIED = 1142


def _order(order_no: str) -> SalesOrder:
    return SalesOrder(
        order_no=order_no,
        customer="c",
        total_amount=Decimal("1.00"),
        ordered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.fixture
async def reader(readonly_user_url: URL) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(readonly_user_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def router(mysql_engine: AsyncEngine, reader: AsyncEngine) -> DatabaseRouter:
    async with mysql_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[SalesOrder.__table__])
    return DatabaseRouter(writer=mysql_engine, readers=[reader], sticky_after_write=False)


async def test_writes_go_to_writer_and_reads_to_select_only_reader(
    router: DatabaseRouter, reader: AsyncEngine, readonly_user_url: URL
):
    maker = create_routing_sessionmaker(router)
    async with maker() as session:
        session.add(_order("RW-1"))
        await session.commit()  # reader 로 갔다면 1142

    async with maker() as session:
        assert (await session.execute(select(SalesOrder.order_no))).scalars().all() == ["RW-1"]
        served_by = (await session.execute(select(func.current_user()))).scalar_one()
        assert served_by.startswith(f"{readonly_user_url.username}@")

    with pytest.raises((OperationalError, ProgrammingError)) as excinfo:
        async with reader.begin() as conn:
            await conn.execute(text("DELETE FROM sales_orders"))
    assert driver_error_code(excinfo.value) == MYSQL_TABLE_ACCESS_DENIED


async def test_read_only_session_rejects_writes_before_reaching_mysql(router: DatabaseRouter):
    maker = create_routing_sessionmaker(router)
    async with maker() as session:
        session.add(_order("RO-0"))
        await session.commit()

    async with maker() as session:
        mark_read_only(session)
        session.add(_order("RO-1"))
        with pytest.raises(ReadOnlyRoutingError):
            await session.flush()
        await session.rollback()
        with pytest.raises(ReadOnlyRoutingError):
            await session.execute(write_intent(text("DELETE FROM sales_orders")))

    async with maker() as session:
        assert (
            await session.execute(select(func.count()).select_from(SalesOrder))
        ).scalar_one() == 1
