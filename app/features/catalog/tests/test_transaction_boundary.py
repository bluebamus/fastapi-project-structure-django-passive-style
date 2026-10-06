"""Catalog 트랜잭션 경계 (TEST-002).

`blog` 의 같은 이름 파일과 성질이 같다. 새 예제가 그 계약을 물려받았는지 확인한다 —
예제가 "Repository 구현만 다르다"(ADR-002)를 보여주려면 트랜잭션 경계부터 같아야 한다.

1. 읽기 경로는 커밋하지 않는다
2. 쓰기 성공은 정확히 1회 커밋한다
3. 예외 경로는 커밋 없이 끝난다

**"커밋 실패가 2xx 로 둔갑하지 않는다" 는 여기 없다.** 그것은 앱 성질이 아니라
**FastAPI 거동**(yield 의존성의 종료 코드가 응답 전송 앞에 도는가)이고, 앱마다 재면
프레임워크를 앱 수만큼 시험하는 것이다. 정본은 `blog` 의 같은 이름 파일 하나다 —
FastAPI 상향 때 거기가 먼저 빨개진다.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.catalog.models.models import Product  # noqa: F401  (register table)
from main import app

_NEW = {"sku": "SKU-TX", "name": "경계 검증", "price": "1000.00", "stock": 1}
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


@pytest_asyncio.fixture
async def tx_client():
    """commit/rollback 호출을 집계하는 클라이언트."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    calls = {"commit": 0, "rollback": 0}

    async def _override_get_session():
        async with maker() as session:
            original_commit = session.commit
            original_rollback = session.rollback

            async def _counting_commit(*args, **kwargs):
                calls["commit"] += 1
                return await original_commit(*args, **kwargs)

            async def _counting_rollback(*args, **kwargs):
                calls["rollback"] += 1
                return await original_rollback(*args, **kwargs)

            session.commit = _counting_commit  # type: ignore[method-assign]
            session.rollback = _counting_rollback  # type: ignore[method-assign]
            yield session

    app.dependency_overrides[get_writer_db_session] = _override_get_session
    app.dependency_overrides[get_read_only_db_session] = _override_get_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, calls
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_read_path_does_not_commit(tx_client):
    client, calls = tx_client

    resp = await client.get("/api/v1/catalog/products")

    assert resp.status_code == 200
    assert calls["commit"] == 0, f"읽기 경로가 {calls['commit']}회 커밋함"


async def test_write_path_commits_exactly_once(tx_client):
    client, calls = tx_client

    resp = await client.post("/api/v1/catalog/products", json=_NEW)

    assert resp.status_code == 201
    assert calls["commit"] == 1, f"쓰기 성공이 {calls['commit']}회 커밋함"


async def test_exception_path_rolls_back_without_commit(tx_client):
    client, calls = tx_client

    resp = await client.patch(f"/api/v1/catalog/products/{_MISSING_ID}", json={"stock": 1})

    assert resp.status_code == 404
    assert calls["commit"] == 0, "예외 경로가 커밋함 — 부분 저장 위험"
