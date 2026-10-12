"""SNS CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_writer_db_session 오버라이드)로 검증한다.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.features.sns.models.models import SnsPost  # noqa: F401  (register table)
from main import app
from tests.auth_headers import admin_headers
from tests.session_overrides import sqlite_session_overrides


@pytest_asyncio.fixture
async def client():
    # 조회 엔드포인트는 get_read_only_db_session 을 쓴다 — 헬퍼가 두 의존성을 함께
    # 오버라이드한다(읽기 경로가 실제 MySQL 로 새지 않고, 몰래 쓰면 거부된다).
    async with sqlite_session_overrides(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=admin_headers()
        ) as c:
            yield c


def test_sns_auto_registered():
    """디렉터리 컨벤션만으로 sns CRUD 라우터가 자동 발견·마운트된다."""
    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    paths = set(app.openapi()["paths"])
    assert "/api/v1/sns/posts" in paths
    assert "/api/v1/sns/posts/{post_id}" in paths


async def test_create_and_get_post(client):
    resp = await client.post(
        "/api/v1/sns/posts",
        json={"content": "오늘 날씨 좋다", "author": "park"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["content"] == "오늘 날씨 좋다"
    assert body["like_count"] == 0
    post_id = body["id"]

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 200
    # 본문의 author 는 무시되고 서버가 인증 주체(관리자 헤더)의 username 으로 채운다(ADR-018).
    assert got.json()["author"] == "admin"


async def test_list_posts(client):
    await client.post("/api/v1/sns/posts", json={"content": "a"})
    await client.post("/api/v1/sns/posts", json={"content": "b"})

    resp = await client.get("/api/v1/sns/posts")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "old"})
    post_id = created.json()["id"]

    resp = await client.patch(f"/api/v1/sns/posts/{post_id}", json={"content": "new"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "new"


async def test_delete_post(client):
    created = await client.post("/api/v1/sns/posts", json={"content": "c"})
    post_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/sns/posts/{post_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/sns/posts/{post_id}")
    assert got.status_code == 404


async def test_get_missing_post_returns_404(client):
    resp = await client.get("/api/v1/sns/posts/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "SNS_POST_NOT_FOUND"


async def test_create_rejects_empty_content(client):
    resp = await client.post("/api/v1/sns/posts", json={"content": ""})
    assert resp.status_code == 422
