"""엔드포인트 테스트의 세션 오버라이드 계약 (service-hardening C1).

``tests/session_overrides.py`` 가 운영 의존성과 같은 표시(``using_writer`` /
``mark_read_only``)를 붙인 세션을 넣는지, 그리고 다른 테스트가 그 헬퍼를 건너뛰고 세션
의존성을 손으로 오버라이드하지 않는지 본다. 손으로 쓰던 시절에는 read-only 오버라이드가
맨 세션이라 GET 핸들러가 몰래 써도 테스트가 초록이었다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.router import ReadOnlyRoutingError, is_read_only_session
from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.blog.models.models import Post
from tests.session_overrides import sqlite_session_overrides

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "tests" / "session_overrides.py"
SESSION_DEPENDENCIES = {"get_read_only_db_session", "get_writer_db_session"}

#: 라우터의 writer 고정 표시 키. 공개 조회 helper 가 없어 키를 직접 본다 — 이름이 바뀌면
#: 아래 테스트가 실패해 함께 고치게 된다(조용히 통과하지 않는다).
_WRITER_PINNED = "_db_router_writer_pinned"


def _probe_app() -> FastAPI:
    """읽기 전용 의존성으로 **몰래 쓰는** GET 과, writer 세션 상태를 보여 주는 GET."""
    probe = FastAPI()

    @probe.get("/sneaky-write")
    async def sneaky_write(session: AsyncSession = Depends(get_read_only_db_session)) -> dict:
        session.add(Post(title="몰래", content="쓰기"))
        await session.flush()
        return {"written": True}

    @probe.get("/writer-state")
    async def writer_state(session: AsyncSession = Depends(get_writer_db_session)) -> dict:
        return {
            "pinned": bool(session.sync_session.info.get(_WRITER_PINNED)),
            "read_only": is_read_only_session(session),
        }

    return probe


async def test_read_only_override_rejects_a_sneaky_write():
    """read-only 오버라이드로 받은 세션에서 flush 하면 운영과 같이 거부된다."""
    probe = _probe_app()
    async with sqlite_session_overrides(probe):
        transport = ASGITransport(app=probe)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            with pytest.raises(ReadOnlyRoutingError):
                await client.get("/sneaky-write")


async def test_writer_override_is_pinned_to_the_writer():
    """writer 오버라이드는 ``using_writer`` 를 거친다 — 읽기 전용 표시는 없다."""
    probe = _probe_app()
    async with sqlite_session_overrides(probe):
        transport = ASGITransport(app=probe)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/writer-state")

    assert resp.json() == {"pinned": True, "read_only": False}


def _hand_rolled_overrides(path: Path) -> list[str]:
    """``<x>.dependency_overrides[get_*_db_session]`` 첨자를 찾는다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "dependency_overrides"
            and isinstance(node.slice, ast.Name)
            and node.slice.id in SESSION_DEPENDENCIES
        ):
            hits.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return hits


def test_detector_sees_the_helper_itself():
    """탐지기가 헛돌지 않는다 — 헬퍼 자신의 오버라이드 두 줄을 찾아야 한다."""
    assert len(_hand_rolled_overrides(HELPER)) == 2


def test_session_dependencies_are_overridden_only_through_the_helper():
    """세션 의존성을 손으로 오버라이드하는 테스트가 없다 — 표시가 빠진 세션이 다시 생긴다."""
    offenders = [
        hit
        for root in (REPO_ROOT / "app", REPO_ROOT / "tests")
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path != HELPER
        for hit in _hand_rolled_overrides(path)
    ]

    assert not offenders, (
        f"세션 의존성을 손으로 오버라이드한다: {offenders} — "
        "tests/session_overrides.py 의 sqlite_session_overrides 를 쓸 것"
    )
