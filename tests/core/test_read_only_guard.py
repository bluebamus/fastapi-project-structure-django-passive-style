"""읽기 전용 세션의 쓰기 차단은 ``DB_ROUTER_ENABLED`` 와 무관해야 한다.

차단이 ``RoutingSession.get_bind()`` 안에만 있으면, 라우터가 꺼진 구성(기본값)과
background 세션 팩토리에서는 ``mark_read_only()`` 를 불러도 쓰기가 그냥 통과한다.
``RawCRUDBase`` 의 검사도 그 클래스를 거치는 호출에만 걸린다 — 세션에 직접 던지는
ORM flush·Core DML·Raw SQL 은 아무 데도 걸리지 않는다.

read-only 는 replica 라우팅 옵션이 아니라 **Dependency 계약**이므로, 두 구성
(router on/off) 모두에서 같은 결과여야 한다. 이 파일이 그 계약을 고정한다.

판별은 이 저장소의 **명시 의도 태그** 계약을 따른다 — Raw ``text()`` 는
``read_intent()`` 가 붙은 것만 읽기로 보고, 태그가 없으면 거부한다(fail-closed).

테스트 모델은 별도 ``DeclarativeBase`` 를 쓴다 — 공유 metadata 와 migration 을
오염시키지 않기 위해서다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Integer, String, delete, insert, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    read_intent,
    write_intent,
)


class _GuardBase(DeclarativeBase):
    """테스트 전용 metadata — 앱 Base 와 분리한다."""


class Widget(_GuardBase):
    __tablename__ = "guard_widgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50))


@pytest.fixture(params=["router_off", "router_on"])
async def maker(request):
    """라우터 on/off 두 구성을 같은 계약으로 검증한다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 커넥션 1개 유지 → :memory: DB 가 살아있다
    )
    async with engine.begin() as connection:
        await connection.run_sync(_GuardBase.metadata.create_all)

    if request.param == "router_on":
        factory = create_routing_sessionmaker(DatabaseRouter(writer=engine, readers=[]))
    else:
        factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)

    async with factory() as seed:
        await seed.execute(insert(Widget).values(id=1, name="seed"))
        await seed.commit()

    yield factory
    await engine.dispose()


@pytest.fixture
async def read_only(maker):
    async with maker() as session:
        mark_read_only(session)
        yield session


# =============================================================================
# 쓰기는 거부된다 — RawCRUDBase 를 거치지 않는 경로가 요점이다
# =============================================================================
async def test_orm_flush_is_blocked(read_only):
    """``session.add()`` + flush 는 어느 구성에서도 막힌다."""
    read_only.add(Widget(id=2, name="written"))

    with pytest.raises(ReadOnlyRoutingError):
        await read_only.flush()


@pytest.mark.parametrize(
    ("label", "statement"),
    [
        ("INSERT", insert(Widget).values(id=3, name="core")),
        ("UPDATE", update(Widget).where(Widget.id == 1).values(name="core")),
        ("DELETE", delete(Widget).where(Widget.id == 1)),
    ],
)
async def test_core_dml_is_blocked(read_only, label: str, statement):
    """Core DML 을 세션에 직접 던져도 막힌다 — RawCRUDBase 를 거치지 않는 경로."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(statement)


async def test_untagged_raw_insert_is_blocked(read_only):
    """의도 태그 없는 Raw INSERT — 마지막 방어선."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text("INSERT INTO guard_widgets (id, name) VALUES (4, 'raw')"))


async def test_untagged_raw_select_is_blocked(read_only):
    """태그 없는 Raw SELECT 도 거부된다(fail-closed) — 판별 근거가 태그뿐이다."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(text("SELECT name FROM guard_widgets"))


async def test_write_intent_text_is_blocked(read_only):
    """``write_intent()`` 가 붙은 구문은 SQL 모양과 무관하게 거부된다."""
    with pytest.raises(ReadOnlyRoutingError):
        await read_only.execute(write_intent(text("SELECT name FROM guard_widgets")))


# =============================================================================
# 과차단도 결함이다 — 읽기는 통과해야 한다
# =============================================================================
async def test_orm_select_is_allowed(read_only):
    result = await read_only.execute(select(Widget.name).order_by(Widget.id))

    assert list(result.scalars().all()) == ["seed"]


async def test_read_intent_text_is_allowed(read_only):
    result = await read_only.execute(read_intent(text("SELECT name FROM guard_widgets")))

    assert result.scalar() == "seed"
