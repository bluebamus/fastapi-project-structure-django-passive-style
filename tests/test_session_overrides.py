"""엔드포인트 테스트의 세션 오버라이드 계약.

``tests/session_overrides.py`` 가 운영 의존성과 같은 표시(``using_writer`` /
``mark_read_only``)를 붙인 세션을 넣는지 본다. 표시가 빠지면 GET 핸들러가 몰래 써도 테스트가 초록이 된다.
"""

from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.router import ReadOnlyRoutingError, is_read_only_session
from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.blog.models.models import Post
from tests.session_overrides import sqlite_session_overrides

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
