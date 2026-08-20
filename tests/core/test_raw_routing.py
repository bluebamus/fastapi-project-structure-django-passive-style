"""Phase 4 — Raw SQL 의 읽기/쓰기 라우팅 (requirements RAW-REP-007).

``text()`` 는 문자열이라 라우터가 타입으로 성격을 알 수 없다. 첫 토큰을 파싱하는 방법은
``WITH x AS (...) DELETE ...`` 같은 CTE DML 을 읽기로 오판한다 — 그러면 DML 이 replica 로
가거나(오라우팅) 읽기 전용 세션을 그대로 통과한다.

그래서 SQL 을 해석하는 대신 **호출부가 의도를 붙인다**. 이 파일은 그 의도가 실제로
바인딩을 바꾸는지를 **결과값으로** 증명한다 — writer/reader 두 엔진에 서로 다른 행을
심어두고, 돌아온 값이 어느 쪽 것인지 본다. 계약 문장이 아니라 실행 결과다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
)
from app.core.repositories.raw_repository_base import RawRepositoryBase

QUERY = "probe.route"


class ProbeRawRepository(RawRepositoryBase):
    """도메인 SQL 없는 얇은 상속 — 라우팅만 본다."""


async def _make_engine(origin: str) -> AsyncEngine:
    """``origin`` 행 하나가 들어 있는 독립 in-memory SQLite 엔진."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 커넥션 1개 유지 → :memory: DB 가 살아있다
    )
    async with engine.begin() as connection:
        await connection.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, origin TEXT)"))
        await connection.execute(
            text("INSERT INTO probe (id, origin) VALUES (1, :origin)"), {"origin": origin}
        )
    return engine


@pytest.fixture
async def routed():
    """writer/reader 가 분리된 라우팅 세션과 두 엔진."""
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))
    async with maker() as session:
        yield session
    await writer.dispose()
    await reader.dispose()


async def _origin(repo: ProbeRawRepository, **kwargs) -> str:
    return await repo.fetch_scalar(
        text("SELECT origin FROM probe WHERE id = 1"), query_name=QUERY, **kwargs
    )


# =============================================================================
# 의도가 바인딩을 결정한다
# =============================================================================
async def test_read_intent_goes_to_the_reader(routed):
    """조회는 replica 로 나간다 — 그러라고 replica 를 둔 것이다."""
    assert await _origin(ProbeRawRepository(routed)) == "reader"


async def test_locking_read_goes_to_the_writer(routed):
    """``FOR UPDATE`` 는 쓰기로 본다 — replica 에서 잠근 행은 아무것도 보호하지 않는다."""
    assert await _origin(ProbeRawRepository(routed), for_update=True) == "writer"


async def test_write_lands_on_the_writer_engine():
    """Raw DML 이 replica 로 가면 조용히 사라진다.

    같은 세션으로 되읽어 확인하면 안 된다 — 쓰기가 replica 로 갔어도 그 세션은
    같은 replica 를 다시 읽어 "성공"처럼 보인다. 그래서 **엔진에 직접** 물어본다.
    """
    writer = await _make_engine("writer")
    reader = await _make_engine("reader")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))

    try:
        async with maker() as session:
            await ProbeRawRepository(session).execute(
                text("UPDATE probe SET origin = :origin WHERE id = 1"),
                {"origin": "touched"},
                query_name="probe.touch",
            )
            await session.commit()

        async with writer.connect() as connection:
            landed = (await connection.execute(text("SELECT origin FROM probe"))).scalar()
        async with reader.connect() as connection:
            untouched = (await connection.execute(text("SELECT origin FROM probe"))).scalar()
    finally:
        await writer.dispose()
        await reader.dispose()

    assert landed == "touched", "Raw UPDATE 가 writer 에 도달하지 않았다"
    assert untouched == "reader", "Raw UPDATE 가 replica 로 갔다 — 복제로 덮어써지며 사라진다"


async def test_unclassified_statement_never_reaches_the_reader(routed):
    """의도를 붙이지 않은 ``text()`` 는 reader 로 보내지 않는다 (fail-closed).

    Raw Base 를 거치지 않고 세션에 직접 던지는 코드가 언젠가 생긴다. 그게 DML 이면
    replica 로 가서는 안 되고, 그게 SELECT 인지 DML 인지 라우터는 모른다. 모를 때는
    writer 로 보낸다 — 잘못 보내도 손해는 SELECT 하나가 primary 로 가는 것뿐이다.
    """
    result = await routed.execute(text("SELECT origin FROM probe WHERE id = 1"))

    assert result.scalar() == "writer"


# =============================================================================
# 읽기 전용 세션 — 우회 경로가 없어야 한다
# =============================================================================
@pytest.mark.parametrize(
    ("label", "sql"),
    [
        ("일반 DML", "DELETE FROM probe WHERE id = 1"),
        ("소문자", "delete from probe where id = 1"),
        ("선행 공백", "   \n\t DELETE FROM probe WHERE id = 1"),
        ("선행 주석", "-- 무해해 보이는 주석\nDELETE FROM probe WHERE id = 1"),
        ("블록 주석", "/* SELECT */ DELETE FROM probe WHERE id = 1"),
        ("CTE DML", "WITH doomed AS (SELECT id FROM probe) DELETE FROM probe WHERE id = 1"),
        ("INSERT", "INSERT INTO probe (id, origin) VALUES (2, 'x')"),
        ("UPDATE", "UPDATE probe SET origin = 'x' WHERE id = 1"),
    ],
)
async def test_raw_dml_is_blocked_on_a_read_only_session(routed, label: str, sql: str):
    """어떤 모양으로 감싸도 읽기 전용 세션에서는 실행되지 않는다.

    첫 토큰 파싱이었다면 소문자·공백·주석은 버텨도 CTE 에서 뚫린다. 여기서는 SQL 을
    보지 않고 의도로 판정하므로 여덟 경우가 같은 이유로 막힌다.
    """
    mark_read_only(routed)
    repo = ProbeRawRepository(routed)

    with pytest.raises(ReadOnlyRoutingError):
        await repo.execute(text(sql), query_name="probe.dml")


async def test_unclassified_dml_is_blocked_on_a_read_only_session(routed):
    """Raw Base 를 우회해 세션에 직접 던져도 막힌다 — 마지막 방어선."""
    mark_read_only(routed)

    with pytest.raises(ReadOnlyRoutingError):
        await routed.execute(
            text("WITH doomed AS (SELECT id FROM probe) DELETE FROM probe WHERE id = 1")
        )


async def test_read_still_reaches_the_reader_on_a_read_only_session(routed):
    """과차단도 결함이다 — 읽기 전용 세션의 읽기는 여전히 replica 로 간다."""
    mark_read_only(routed)

    assert await _origin(ProbeRawRepository(routed)) == "reader"
