"""BaseRepository.update 빈 patch 회귀 테스트.

빈 dict 를 update 에 넘기면 예전에는 update().values() 의 빈 SET 절 때문에
SQLAlchemy CompileError → DatabaseException(HTTP 500) 이 발생했다. 이제는
no-op 로 처리해 대상이 있으면 현재 행을 그대로 반환(→200)해야 한다.
"""

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.repositories.repository_base import BaseRepository
from app.domains.user.models.models import User


class _UserRepo(BaseRepository[User]):
    model = User


@pytest_asyncio.fixture
async def repo():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield _UserRepo(session)
    await engine.dispose()


async def test_update_empty_patch_is_noop(repo):
    created = await repo.create({"username": "kim", "email": "kim@ex.com"})

    result = await repo.update(created.id, {})  # 빈 patch

    assert result is not None
    assert result.id == created.id
    assert result.username == "kim"  # 변경 없음


async def test_update_empty_patch_missing_returns_none(repo):
    result = await repo.update("does-not-exist", {})
    assert result is None
