"""User CRUD 엔드포인트 테스트.

표준 include_router 배선 + view→dependency→service→repository→DB 전체 경로를
in-memory sqlite(get_writer_db_session 오버라이드)로 검증한다. 쓰기용 서비스는
refresh 기록(Redis)을 주입받으므로 ``get_redis`` 를 fakeredis 로 바꾼다.

인가(service-hardening F2): 목록·생성·삭제는 슈퍼유저, 단건 조회·수정은 본인 또는
슈퍼유저, 권한 필드(``is_active``·``is_superuser``)는 슈퍼유저만 바꾼다.
"""

import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient

from app.core.redis import get_redis
from app.core.security.dependencies import get_password_hasher
from app.features.user.models.models import User
from main import app
from tests.auth_headers import admin_headers, bearer
from tests.session_overrides import sqlite_session_overrides


@pytest_asyncio.fixture
async def env():
    """(관리자 클라이언트, 세션 팩토리, fakeredis)."""
    # 조회 엔드포인트는 get_read_only_db_session 을 쓴다 — 헬퍼가 두 의존성을 함께
    # 오버라이드한다(읽기 경로가 실제 MySQL 로 새지 않고, 몰래 쓰면 거부된다).
    async with sqlite_session_overrides(app) as maker:
        redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: redis
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=admin_headers()
        ) as c:
            yield c, maker, redis


@pytest_asyncio.fixture
async def client(env):
    return env[0]


async def _create(client, username: str, **extra) -> dict:
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": username, "email": f"{username}@x.com", "password": "pw-12345678"}
        | extra,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _as(user: dict) -> dict[str, str]:
    """생성된 사용자 본인의 헤더(일반 사용자)."""
    return bearer(user["id"], user["username"])


def test_user_auto_registered():
    """디렉터리 컨벤션만으로 user CRUD 라우터가 자동 발견·마운트된다."""
    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    paths = set(app.openapi()["paths"])
    assert "/api/v1/user/users" in paths
    assert "/api/v1/user/users/{user_id}" in paths


async def test_create_and_get_user(client):
    body = await _create(client, "alice")
    assert body["username"] == "alice"
    assert body["is_active"] is True
    assert body["is_superuser"] is False
    assert "password" not in body and "hashed_password" not in body

    got = await client.get(f"/api/v1/user/users/{body['id']}")
    assert got.status_code == 200
    assert got.json()["email"] == "alice@x.com"


async def test_create_stores_an_argon2_hash(env):
    """생성은 비밀번호를 core ``PasswordHasher`` 로 해시해 저장한다(평문·무비밀번호 금지, F-023)."""
    client, maker, _ = env
    body = await _create(client, "hashme")

    async with maker() as session:
        user = await session.get(User, body["id"])
    assert user is not None and user.hashed_password is not None
    stored = user.hashed_password
    assert stored.startswith("$argon2")
    assert get_password_hasher().verify_and_update("pw-12345678", stored)[0] is True


async def test_create_requires_a_password(client):
    resp = await client.post("/api/v1/user/users", json={"username": "nopw", "email": "n@x.com"})
    assert resp.status_code == 422


async def test_superuser_can_create_a_superuser(client):
    body = await _create(client, "root2", is_superuser=True)
    assert body["is_superuser"] is True


async def test_list_users(client):
    await _create(client, "a")
    await _create(client, "b")

    resp = await client.get("/api/v1/user/users")
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


async def test_update_user_deactivate(client):
    user_id = (await _create(client, "bob"))["id"]

    resp = await client.patch(f"/api/v1/user/users/{user_id}", json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


async def test_delete_user(client):
    user_id = (await _create(client, "carol"))["id"]

    resp = await client.delete(f"/api/v1/user/users/{user_id}")
    assert resp.status_code == 204

    got = await client.get(f"/api/v1/user/users/{user_id}")
    assert got.status_code == 404


async def test_duplicate_username_returns_409(client):
    await _create(client, "dup")
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "dup", "email": "d2@x.com", "password": "pw-12345678"},
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "USER_USERNAME_DUPLICATE"


async def test_get_missing_user_returns_404(client):
    resp = await client.get("/api/v1/user/users/nonexistent-id")
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "USER_NOT_FOUND"


async def test_create_rejects_invalid_email(client):
    resp = await client.post(
        "/api/v1/user/users",
        json={"username": "x", "email": "not-an-email", "password": "pw-12345678"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 본인 또는 슈퍼유저
# ---------------------------------------------------------------------------
async def test_user_reads_and_updates_self(client):
    me = await _create(client, "self")

    got = await client.get(f"/api/v1/user/users/{me['id']}", headers=_as(me))
    assert got.status_code == 200

    resp = await client.patch(
        f"/api/v1/user/users/{me['id']}", json={"email": "new@x.com"}, headers=_as(me)
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "new@x.com"


async def test_user_cannot_read_or_update_someone_else(client):
    me = await _create(client, "me")
    other = await _create(client, "other")

    got = await client.get(f"/api/v1/user/users/{other['id']}", headers=_as(me))
    patched = await client.patch(
        f"/api/v1/user/users/{other['id']}", json={"email": "x@x.com"}, headers=_as(me)
    )

    assert (got.status_code, patched.status_code) == (403, 403)
    assert got.json()["error_code"] == "FORBIDDEN"


async def test_authorization_is_decided_before_existence(client):
    """없는 ID 도 403 이다 — 404/403 차이로 다른 사용자 ID 의 존재를 알아내지 못한다."""
    me = await _create(client, "prober")

    got = await client.get("/api/v1/user/users/no-such-id", headers=_as(me))
    patched = await client.patch(
        "/api/v1/user/users/no-such-id", json={"email": "x@x.com"}, headers=_as(me)
    )

    assert (got.status_code, patched.status_code) == (403, 403)


async def test_user_cannot_change_privileged_fields_on_self(client):
    me = await _create(client, "climber")

    for field, value in (("is_superuser", True), ("is_active", True)):
        resp = await client.patch(
            f"/api/v1/user/users/{me['id']}", json={field: value}, headers=_as(me)
        )
        assert resp.status_code == 403, field

    got = await client.get(f"/api/v1/user/users/{me['id']}")
    assert got.json()["is_superuser"] is False


async def test_normal_user_cannot_list_create_or_delete(client):
    me = await _create(client, "plain")

    listed = await client.get("/api/v1/user/users", headers=_as(me))
    created = await client.post(
        "/api/v1/user/users",
        json={"username": "z", "email": "z@x.com", "password": "pw-12345678"},
        headers=_as(me),
    )
    deleted = await client.delete(f"/api/v1/user/users/{me['id']}", headers=_as(me))

    assert (listed.status_code, created.status_code, deleted.status_code) == (403, 403, 403)


# ---------------------------------------------------------------------------
# 비활성화·강등·삭제 → refresh 폐기
# ---------------------------------------------------------------------------
async def _seed_family(redis: FakeRedis, user_id: str) -> None:
    from app.core.security.dependencies import get_refresh_token_store

    await get_refresh_token_store(redis).register("jti-1", user_id, "fam-1")


async def _revoked(redis: FakeRedis) -> bool:
    return bool(await redis.exists("auth:fam:fam-1:revoked"))


async def test_deactivation_revokes_refresh_families(env):
    client, _, redis = env
    user_id = (await _create(client, "deact"))["id"]
    await _seed_family(redis, user_id)

    resp = await client.patch(f"/api/v1/user/users/{user_id}", json={"is_active": False})

    assert resp.status_code == 200
    assert await _revoked(redis)


async def test_demotion_revokes_refresh_families(env):
    client, _, redis = env
    user_id = (await _create(client, "demote", is_superuser=True))["id"]
    await _seed_family(redis, user_id)

    resp = await client.patch(f"/api/v1/user/users/{user_id}", json={"is_superuser": False})

    assert resp.status_code == 200
    assert await _revoked(redis)


async def test_plain_update_keeps_refresh_families(env):
    client, _, redis = env
    user_id = (await _create(client, "keep"))["id"]
    await _seed_family(redis, user_id)

    await client.patch(f"/api/v1/user/users/{user_id}", json={"email": "k2@x.com"})

    assert not await _revoked(redis)


async def test_delete_revokes_refresh_families(env):
    client, _, redis = env
    user_id = (await _create(client, "gone"))["id"]
    await _seed_family(redis, user_id)

    resp = await client.delete(f"/api/v1/user/users/{user_id}")

    assert resp.status_code == 204
    assert await _revoked(redis)
