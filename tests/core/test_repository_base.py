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

from app.core.exception import DuplicateException
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


# =============================================================================
# 조회
# =============================================================================
async def test_get_by_id(repo: WidgetRepository, seeded: list[Widget]):
    assert (await repo.get_by_id("w1")).name == "alpha"
    assert await repo.get_by_id("nope") is None


async def test_get_one_and_all(repo: WidgetRepository, seeded: list[Widget]):
    assert (await repo.get_one(name="gamma")).id == "w3"
    assert await repo.get_one(name="missing") is None
    assert len(await repo.get_all()) == 3
    assert len(await repo.get_all(limit=2)) == 2


async def test_count_and_exists(repo: WidgetRepository, seeded: list[Widget]):
    assert await repo.count() == 3
    assert await repo.count(kind="special") == 1
    assert await repo.exists("w1") is True
    assert await repo.exists("nope") is False


# =============================================================================
# 수정 / 삭제
# =============================================================================
async def test_update_and_missing_update(repo: WidgetRepository, seeded: list[Widget]):
    updated = await repo.update("w1", {"kind": "special"})

    assert updated is not None and updated.kind == "special"
    assert await repo.update("nope", {"kind": "x"}) is None


async def test_delete_paths(repo: WidgetRepository, seeded: list[Widget]):
    assert await repo.delete("w1") is True
    assert await repo.delete("w1") is False, "이미 지운 행을 다시 지우면 False"
    assert await repo.count() == 2


# =============================================================================
# upsert 계열
# =============================================================================


# =============================================================================
# rowcount 의미 분리 (Phase 3a · ledger F-021)
# =============================================================================
async def test_update_with_unchanged_values_still_returns_the_row(session: AsyncSession):
    """값이 그대로인 PATCH 도 리소스를 돌려준다 — 404 가 아니다.

    MySQL 의 UPDATE ``rowcount`` 는 **값이 바뀐** 행 수다. 같은 값으로 덮어쓰면
    행이 멀쩡히 있어도 0 이 나온다. 그걸 "행이 없다"로 읽으면 존재하는 리소스에
    404 를 돌려주게 된다 — 클라이언트가 재시도해도 영원히 404 다.
    """
    repo = WidgetRepository(session)
    created = await repo.create({"name": "unchanged", "kind": "basic"})

    updated = await repo.update(created.id, {"kind": "basic"})  # 같은 값

    assert updated is not None, "no-op PATCH 가 404 로 취급됐다"
    assert updated.id == created.id
    assert updated.kind == "basic"


async def test_update_of_a_missing_row_returns_none(session: AsyncSession):
    """진짜 없는 행은 여전히 None — 404 의 의미를 잃지 않는다."""
    repo = WidgetRepository(session)

    assert await repo.update("존재하지-않는-id", {"kind": "x"}) is None


# =============================================================================
# 공개 계약 (Phase 3b · ADR-016)
# =============================================================================
#: BaseRepository 가 공개하는 **전부**. 기능 코드가 실제로 쓰던 7개에 ``exists`` 를
#: 더한 8개다(Phase 0 기준선 `baseline/repository-public-api.md` 근거).
PUBLIC_CONTRACT = frozenset(
    {"create", "get_by_id", "get_one", "get_all", "count", "exists", "update", "delete"}
)


def test_public_contract_is_exactly_these_eight():
    """계약이 넓어지지 않았는지 본다.

    넓은 계약은 두 배로 비싸다 — ORM/Raw 가 "Repository 구현만 다르다"(ADR-002)를
    지키려면 여기 있는 것을 **Raw 에서도 전부** 구현해야 한다. 편의 메서드를 하나씩
    더하다 보면 그 비용이 조용히 늘어난다.

    새 메서드가 필요하면 기능별 Repository 에 둔다. 정말 공통이면 이 목록과
    charter §2-3 을 함께 고친다.
    """
    import ast
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2] / "app" / "core" / "repositories" / "repository_base.py"
    ).read_text(encoding="utf-8")

    class_node = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.ClassDef) and node.name == "BaseRepository"
    )
    public = {
        node.name
        for node in class_node.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.name.startswith("_")
    }

    assert public == set(PUBLIC_CONTRACT), (
        f"공개 계약이 바뀌었다.\n  추가됨: {sorted(public - PUBLIC_CONTRACT)}\n"
        f"  사라짐: {sorted(PUBLIC_CONTRACT - public)}"
    )


@pytest.mark.parametrize(
    "removed",
    [
        "bulk_create",
        "get_by_id_or_raise",
        "get_many",
        "exists_by",
        "get_by_id_with",
        "get_one_with",
        "get_many_with",
        "get_all_with",
        "get_by_ids_with",
        "get_partial",
        "get_by_id_partial",
        "get_in_batches",
        "get_with_join",
        "count_with_relation",
        "bulk_update",
        "update_by",
        "bulk_delete",
        "delete_by",
        "get_or_create",
        "update_or_create",
    ],
)
def test_removed_methods_do_not_come_back(removed: str):
    """지운 메서드가 되살아나지 않았는지 — "같은 객체인가"가 아니라 "없는가"를 본다."""
    assert not hasattr(BaseRepository, removed), (
        f"{removed} 이 다시 생겼다. 정말 필요하면 기능별 Repository 에 두고, "
        "공통이어야 한다면 PUBLIC_CONTRACT 와 charter 를 함께 고쳐라"
    )


async def test_primary_key_type_is_a_parameter():
    """PK 타입이 계약에 노출된다 — ``str`` 로 뭉개지 않는다.

    기본값이 있어 기존 ``BaseRepository[Widget]`` 표기는 그대로 동작한다.
    """
    import inspect

    from app.core.repositories.crud_base import PrimaryKeyT

    assert PrimaryKeyT.__name__ == "PrimaryKeyT"

    # `from __future__ import annotations` 여부에 따라 문자열/객체가 갈리므로 둘 다 받는다.
    for method in (BaseRepository.get_by_id, BaseRepository.update, BaseRepository.delete):
        annotation = inspect.signature(method).parameters["id"].annotation
        assert annotation in (
            "PrimaryKeyT",
            PrimaryKeyT,
        ), f"{method.__name__} 의 id 가 PK 타입 파라미터를 쓰지 않는다: {annotation}"
