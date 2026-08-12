"""``BaseRepository`` 의 공용 CRUD 계약 (NFR-08 커버리지 포함).

이 class 는 템플릿 사용자가 새 기능마다 상속하는 코드다 — 여기서 조용히 깨지면
모든 앱이 함께 깨진다. 그런데 기존 테스트는 기능별 Repository 의 얇은 wrapper 만
지나가서, 정작 로직이 있는 base 는 대부분 실행되지 않았다.

SQLite in-memory 로 실제 세션을 만들어 돌린다 — mock 으로는 "쿼리가 실제로 동작하는가"
를 검증할 수 없고, 이 class 가 하는 일이 정확히 그것이다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.exception import DuplicateException, NotFoundException
from app.core.repositories.repository_base import BaseRepository


class Base(DeclarativeBase):
    """이 테스트 전용 declarative base (실제 앱 metadata 와 분리)."""


class Widget(Base):
    __tablename__ = "repo_base_widgets"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    kind: Mapped[str] = mapped_column(default="basic")


class WidgetRepository(BaseRepository[Widget]):
    model = Widget


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def repo(session: AsyncSession) -> WidgetRepository:
    return WidgetRepository(session)


@pytest.fixture
async def seeded(repo: WidgetRepository) -> list[Widget]:
    return [
        await repo.create({"id": "w1", "name": "alpha", "kind": "basic"}),
        await repo.create({"id": "w2", "name": "beta", "kind": "basic"}),
        await repo.create({"id": "w3", "name": "gamma", "kind": "special"}),
    ]


# =============================================================================
# 생성
# =============================================================================
async def test_create_assigns_id_when_missing(repo: WidgetRepository):
    created = await repo.create({"name": "auto"})

    assert created.id, "id 를 주지 않으면 생성기가 채워야 한다"
    assert await repo.get_by_id(created.id) is not None


async def test_create_rejects_duplicate(repo: WidgetRepository, seeded: list[Widget]):
    with pytest.raises(DuplicateException):
        await repo.create({"id": "dup", "name": "alpha"})


async def test_bulk_create(repo: WidgetRepository):
    created = await repo.bulk_create([{"name": "b1"}, {"name": "b2"}])

    assert len(created) == 2
    assert await repo.count() == 2


# =============================================================================
# 조회
# =============================================================================
async def test_get_by_id_and_or_raise(repo: WidgetRepository, seeded: list[Widget]):
    assert (await repo.get_by_id("w1")).name == "alpha"
    assert await repo.get_by_id("nope") is None
    assert (await repo.get_by_id_or_raise("w2")).name == "beta"
    with pytest.raises(NotFoundException):
        await repo.get_by_id_or_raise("nope")


async def test_get_one_and_many_and_all(repo: WidgetRepository, seeded: list[Widget]):
    assert (await repo.get_one(name="gamma")).id == "w3"
    assert await repo.get_one(name="missing") is None
    assert len(await repo.get_many(kind="basic")) == 2
    assert len(await repo.get_all()) == 3
    assert len(await repo.get_all(limit=2)) == 2


async def test_count_and_exists(repo: WidgetRepository, seeded: list[Widget]):
    assert await repo.count() == 3
    assert await repo.count(kind="special") == 1
    assert await repo.exists("w1") is True
    assert await repo.exists("nope") is False
    assert await repo.exists_by(name="beta") is True
    assert await repo.exists_by(name="missing") is False


async def test_eager_loading_variants_work_without_relationships(
    repo: WidgetRepository, seeded: list[Widget]
):
    """관계가 없는 모델에서도 ``*_with`` 계열이 정상 동작한다(옵션 없음 경로)."""
    assert (await repo.get_by_id_with("w1")).name == "alpha"
    assert (await repo.get_one_with(name="alpha")).id == "w1"
    assert len(await repo.get_many_with(kind="basic")) == 2
    assert len(await repo.get_all_with()) == 3
    assert len(await repo.get_by_ids_with(["w1", "w3"])) == 2


async def test_partial_column_loading(repo: WidgetRepository, seeded: list[Widget]):
    rows = await repo.get_partial(["id", "name"])
    assert len(rows) == 3

    one = await repo.get_by_id_partial("w1", ["id", "name"])
    assert one is not None and one.id == "w1"
    assert await repo.get_by_id_partial("nope", ["id"]) is None


async def test_get_in_batches(repo: WidgetRepository, seeded: list[Widget]):
    seen: list[str] = []
    async for batch in repo.get_in_batches(batch_size=2):
        seen.extend(widget.id for widget in batch)

    assert sorted(seen) == ["w1", "w2", "w3"]


# =============================================================================
# 수정 / 삭제
# =============================================================================
async def test_update_and_missing_update(repo: WidgetRepository, seeded: list[Widget]):
    updated = await repo.update("w1", {"kind": "special"})

    assert updated is not None and updated.kind == "special"
    assert await repo.update("nope", {"kind": "x"}) is None


async def test_bulk_and_conditional_update(repo: WidgetRepository, seeded: list[Widget]):
    changed = await repo.bulk_update(["w1", "w2"], {"kind": "bulk"})
    assert changed == 2
    assert await repo.count(kind="bulk") == 2

    changed = await repo.update_by({"kind": "renamed"}, kind="special")
    assert changed == 1


async def test_delete_paths(repo: WidgetRepository, seeded: list[Widget]):
    assert await repo.delete("w1") is True
    assert await repo.delete("w1") is False
    assert await repo.bulk_delete(["w2", "w3"]) == 2
    assert await repo.count() == 0


async def test_delete_by_filter(repo: WidgetRepository, seeded: list[Widget]):
    assert await repo.delete_by(kind="basic") == 2
    assert await repo.count() == 1


# =============================================================================
# upsert 계열
# =============================================================================
async def test_get_or_create(repo: WidgetRepository, seeded: list[Widget]):
    existing, created = await repo.get_or_create(name="alpha")
    assert created is False and existing.id == "w1"

    fresh, created = await repo.get_or_create(defaults={"kind": "made"}, name="delta")
    assert created is True and fresh.kind == "made"


async def test_update_or_create(repo: WidgetRepository, seeded: list[Widget]):
    updated, created = await repo.update_or_create(defaults={"kind": "changed"}, name="alpha")
    assert created is False and updated.kind == "changed"

    made, created = await repo.update_or_create(defaults={"kind": "new"}, name="epsilon")
    assert created is True and made.kind == "new"
