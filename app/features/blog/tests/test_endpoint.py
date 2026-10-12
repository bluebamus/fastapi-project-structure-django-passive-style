"""Blog CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_writer_db_session 오버라이드)로 검증한다.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.features.blog.models.models import Post  # noqa: F401  (register table)
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


def test_blog_auto_registered():
    """디렉터리 컨벤션만으로 blog CRUD 라우터가 자동 발견·마운트된다."""
    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    paths = set(app.openapi()["paths"])
    assert "/api/v1/blog/posts" in paths
    assert "/api/v1/blog/posts/{post_id}" in paths


async def test_create_and_get_post(client):
    resp = await client.post(
        "/api/v1/blog/posts",
        json={"title": "첫 글", "content": "본문", "author": "kim"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "첫 글"
    assert body["id"]
    post_id = body["id"]

    got = await client.get(f"/api/v1/blog/posts/{post_id}")
    assert got.status_code == 200
    assert got.json()["content"] == "본문"


async def test_list_posts(client):
    await client.post("/api/v1/blog/posts", json={"title": "a", "content": "x"})
    await client.post("/api/v1/blog/posts", json={"title": "b", "content": "y"})

    resp = await client.get("/api/v1/blog/posts")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2


async def test_update_post(client):
    created = await client.post("/api/v1/blog/posts", json={"title": "old", "content": "c"})
    post_id = created.json()["id"]

    resp = await client.patch(f"/api/v1/blog/posts/{post_id}", json={"title": "new"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "new"
    assert resp.json()["content"] == "c"  # 미전달 필드는 유지


async def test_delete_post(client):
    created = await client.post("/api/v1/blog/posts", json={"title": "t", "content": "c"})
    post_id = created.json()["id"]

    resp = await client.delete(f"/api/v1/blog/posts/{post_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/blog/posts/{post_id}")
    assert got.status_code == 404


async def test_get_missing_post_returns_404(client):
    resp = await client.get("/api/v1/blog/posts/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "BLOG_POST_NOT_FOUND"


async def test_create_rejects_empty_title(client):
    resp = await client.post("/api/v1/blog/posts", json={"title": "", "content": "c"})
    assert resp.status_code == 422
