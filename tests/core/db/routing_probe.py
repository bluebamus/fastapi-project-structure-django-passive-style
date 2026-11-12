"""라우터 테스트 공용 probe — ``origin`` 행 하나로 **어느 엔진이 쿼리를 처리했는지** 결과값으로 증명한다.

``test_router``·``test_replica_fallback`` 이 함께 쓴다. 테스트 모듈끼리 import 하면 한쪽을 지우거나
옮길 때 다른 쪽이 조용히 깨지므로 여기 둔다.
"""

from sqlalchemy import String, insert, select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import StaticPool


class ProbeBase(DeclarativeBase):
    """테스트 전용 메타데이터 (앱 Base 를 오염시키지 않는다)."""


class Probe(ProbeBase):
    __tablename__ = "routing_probe"

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(16))


async def make_engine(origin: str) -> AsyncEngine:
    """`origin` 행 하나가 들어있는 독립 in-memory SQLite 엔진을 만든다."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 커넥션 1개 유지 → :memory: DB 가 살아있다
    )
    async with engine.begin() as conn:
        await conn.run_sync(ProbeBase.metadata.create_all)
        await conn.execute(insert(Probe).values(id=1, origin=origin))
    return engine


async def origins(session) -> list[str]:
    result = await session.execute(select(Probe.origin).order_by(Probe.id))
    return list(result.scalars().all())
