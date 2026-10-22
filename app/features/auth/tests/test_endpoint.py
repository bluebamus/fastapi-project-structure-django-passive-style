"""Auth 엔드포인트 테스트 — register/login/me/refresh/logout 전체 경로.

DB 는 in-memory SQLite(``tests/session_overrides.py``), Redis 는 ``get_redis`` 를 오버라이드한
fakeredis 다 — 레이트 리밋·refresh 회전이 실물 클래스로 돈다(service-hardening ADR-022).
"""

import bcrypt
import jwt
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.redis import get_redis
from app.features.user.models.models import User
from config import jwt_settings
from main import app
from tests.auth_headers import admin_headers
from tests.session_overrides import sqlite_session_overrides

# 상한은 설정에서 읽는다 — 로컬 `.env` 의 값과 무관하게 같은 판정을 한다.
LOGIN_MAX = jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS
LOGIN_IP_MAX = jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS
REGISTER_MAX = jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS


@pytest_asyncio.fixture
async def env():
    """(client, 세션 팩토리, fakeredis)."""
    redis = FakeRedis()
    # 조회 엔드포인트는 get_read_only_db_session 을 쓴다 — 헬퍼가 두 의존성을 함께
    # 오버라이드한다(읽기 경로가 실제 MySQL 로 새지 않고, 몰래 쓰면 거부된다).
    async with sqlite_session_overrides(app) as maker:
        app.dependency_overrides[get_redis] = lambda: redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c, maker, redis
    await redis.aclose()


@pytest_asyncio.fixture
async def client(env):
    return env[0]


async def _register(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@ex.com", "password": password},
    )


async def _login(client, username="alice", password="password123"):
    return await client.post(
        "/api/v1/auth/login", data={"username": username, "password": password}
    )


async def _refresh(client, token):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": token})


async def _logout(client, token):
    return await client.post("/api/v1/auth/logout", json={"refresh_token": token})


def _family(refresh_token: str) -> str:
    """토큰의 family id(검증 없이 읽는다 — 테스트가 Redis 상태를 확인하는 용도)."""
    return jwt.decode(refresh_token, options={"verify_signature": False})["fam"]


async def _family_revoked(redis, refresh_token: str) -> bool:
    return bool(await redis.exists(f"auth:fam:{_family(refresh_token)}:revoked"))


async def _me(client, access):
    return await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})


# ---------------------------------------------------------------------------
# 회원가입 · 로그인 · /me
# ---------------------------------------------------------------------------
async def test_register_returns_user_without_password(client):
    resp = await _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["username"] == "alice"
    assert "password" not in body and "hashed_password" not in body
    assert body["is_active"] is True


async def test_register_stores_an_argon2_hash(env):
    client, maker, _ = env
    await _register(client)

    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password))

    assert stored is not None and stored.startswith("$argon2id$")


async def test_register_duplicate_username_409(client):
    await _register(client)
    resp = await _register(client)
    assert resp.status_code == 409
    assert resp.json()["error_code"] == "AUTH_USERNAME_DUPLICATE"


async def test_register_rejects_short_password(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "bob@ex.com", "password": "short"},
    )
    assert resp.status_code == 422


async def test_login_returns_bearer_pair_with_expiry(client):
    await _register(client)
    login = await _login(client)
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == jwt_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert tokens["access_token"] and tokens["refresh_token"]

    me = await _me(client, tokens["access_token"])
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_wrong_password_401(client):
    await _register(client)
    resp = await _login(client, password="wrong-password")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_unknown_user_401(client):
    resp = await _login(client, username="ghost")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_CREDENTIALS"


async def test_login_inactive_user_401(env):
    client, maker, _ = env
    await _register(client)
    async with maker() as session:
        await session.execute(update(User).values(is_active=False))
        await session.commit()

    assert (await _login(client)).status_code == 401


async def test_legacy_bcrypt_user_logs_in_and_hash_is_migrated(env):
    """이전 코드가 저장한 bcrypt 해시 → 로그인 성공 + Argon2 로 바뀌어 **커밋**된다."""
    client, maker, _ = env
    await _register(client)
    legacy = bcrypt.hashpw(b"password123", bcrypt.gensalt(rounds=4)).decode()
    async with maker() as session:
        await session.execute(update(User).values(hashed_password=legacy))
        await session.commit()

    assert (await _login(client)).status_code == 200

    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password))
    assert stored is not None and stored.startswith("$argon2id$")
    assert (await _login(client)).status_code == 200  # 새 해시로도 로그인된다


async def test_me_without_token_401(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_401(client):
    resp = await _me(client, "not-a-real-token")
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_me_rejects_inactive_user(env):
    client, maker, _ = env
    await _register(client)
    access = (await _login(client)).json()["access_token"]
    async with maker() as session:
        await session.execute(update(User).values(is_active=False))
        await session.commit()

    resp = await _me(client, access)

    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_me_rejects_refresh_token(client):
    await _register(client)
    refresh = (await _login(client)).json()["refresh_token"]

    assert (await _me(client, refresh)).status_code == 401


async def test_me_does_not_need_redis(client):
    """/me 는 토큰 검증 + 읽기 전용 조회뿐이다 — Redis 장애가 /me 를 막지 않는다."""
    await _register(client)
    access = (await _login(client)).json()["access_token"]

    def _no_redis():
        raise AssertionError("/me 가 Redis 를 요구했다")

    app.dependency_overrides[get_redis] = _no_redis
    assert (await _me(client, access)).status_code == 200


# ---------------------------------------------------------------------------
# refresh 회전 · 재사용 탐지 · 로그아웃
# ---------------------------------------------------------------------------
async def test_full_flow_rotation_reuse_detection_and_logout(client):
    await _register(client)
    first = (await _login(client)).json()

    rotated = await _refresh(client, first["refresh_token"])
    assert rotated.status_code == 200
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await _me(client, second["access_token"])).status_code == 200

    # 이미 쓴 refresh 토큰 재사용 → 401, 그리고 같은 family 의 새 토큰도 폐기된다
    reuse = await _refresh(client, first["refresh_token"])
    assert reuse.status_code == 401
    assert reuse.json()["error_code"] == "AUTH_INVALID_TOKEN"
    assert (await _refresh(client, second["refresh_token"])).status_code == 401

    # 새로 로그인한 family 는 영향을 받지 않는다
    third = (await _login(client)).json()
    assert (await _logout(client, third["refresh_token"])).status_code == 204
    assert (await _refresh(client, third["refresh_token"])).status_code == 401


async def test_rotation_chain_keeps_working(client):
    await _register(client)
    token = (await _login(client)).json()["refresh_token"]

    for _ in range(3):
        resp = await _refresh(client, token)
        assert resp.status_code == 200
        token = resp.json()["refresh_token"]


async def test_logout_is_idempotent(env):
    client, _, redis = env
    await _register(client)
    refresh = (await _login(client)).json()["refresh_token"]

    first = await _logout(client, refresh)
    second = await _logout(client, refresh)

    assert (first.status_code, second.status_code) == (204, 204)
    assert first.content == b""
    assert await _family_revoked(redis, refresh)


async def test_logout_rejects_access_token(client):
    await _register(client)
    access = (await _login(client)).json()["access_token"]

    assert (await _logout(client, access)).status_code == 401


async def test_logout_only_revokes_its_own_family(client):
    await _register(client)
    a = (await _login(client)).json()["refresh_token"]
    b = (await _login(client)).json()["refresh_token"]

    await _logout(client, a)

    assert (await _refresh(client, b)).status_code == 200


async def test_refresh_rejects_access_token_401(client):
    await _register(client)
    login = await _login(client)
    resp = await _refresh(client, login.json()["access_token"])
    assert resp.status_code == 401


async def test_refresh_for_deactivated_user_revokes_family(env):
    client, maker, redis = env
    await _register(client)
    refresh = (await _login(client)).json()["refresh_token"]
    async with maker() as session:
        await session.execute(update(User).values(is_active=False))
        await session.commit()

    assert (await _refresh(client, refresh)).status_code == 401
    assert await _family_revoked(redis, refresh)

    # 다시 활성화해도 그 family 는 폐기된 채다 — 소비된 토큰은 재사용으로도 걸린다
    async with maker() as session:
        await session.execute(update(User).values(is_active=True))
        await session.commit()
    assert (await _refresh(client, refresh)).status_code == 401


async def test_refresh_of_revoked_family_with_unconsumed_token_401(env):
    """사용자 단위 폐기(revoke_user) 뒤 아직 쓰지 않은 토큰도 거부된다."""
    client, _, redis = env
    await _register(client)
    refresh = (await _login(client)).json()["refresh_token"]
    fams = await redis.keys("auth:user:*:fams")
    assert len(fams) == 1
    for fam in await redis.smembers(fams[0]):
        await redis.set(f"auth:fam:{fam.decode()}:revoked", "1")

    assert (await _refresh(client, refresh)).status_code == 401


# ---------------------------------------------------------------------------
# 레이트 리밋
# ---------------------------------------------------------------------------
async def test_login_rate_limit_per_username_returns_429_with_retry_after(client):
    await _register(client)
    for _ in range(LOGIN_MAX):
        assert (await _login(client, password="wrong-password")).status_code == 401

    blocked = await _login(client)  # 올바른 비밀번호여도 막힌다

    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["Retry-After"]) <= jwt_settings.AUTH_LOGIN_WINDOW_SECONDS
    body = blocked.json()
    assert body["error_code"] == "TOO_MANY_REQUESTS"
    assert body["detail"]["retry_after"] == int(blocked.headers["Retry-After"])


async def test_login_username_limit_ignores_case(client):
    names = ["Alice", "ALICE", "alice", "aLiCe", "alicE"] * LOGIN_MAX
    for name in names[:LOGIN_MAX]:
        assert (await _login(client, username=name)).status_code == 401

    assert (await _login(client, username="ALIce")).status_code == 429


async def test_successful_login_resets_the_username_counter(client):
    await _register(client)
    for _ in range(LOGIN_MAX - 1):
        await _login(client, password="wrong-password")
    assert (await _login(client)).status_code == 200

    # 초기화되지 않았다면 상한을 넘는 시도라 429 다
    assert (await _login(client, password="wrong-password")).status_code == 401


async def test_login_rate_limit_per_ip(client):
    for i in range(LOGIN_IP_MAX):
        assert (await _login(client, username=f"user{i}")).status_code == 401

    assert (await _login(client, username="someone-new")).status_code == 429


async def test_register_rate_limit_per_ip(client):
    for i in range(REGISTER_MAX):
        assert (await _register(client, username=f"user{i}")).status_code == 201

    blocked = await _register(client, username="user-extra")

    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


# ---------------------------------------------------------------------------
# 인가 연동 (service-hardening F2)
# ---------------------------------------------------------------------------
async def test_admin_deactivation_revokes_refresh_even_after_reactivation(env):
    """관리자가 API 로 비활성화하면 ``revoke_user`` 가 family 를 폐기한다.

    다시 활성화한 뒤 **소비되지 않은** refresh 로 회전해도 401 이다 — 회전 시점의 활성 검사가
    아니라 비활성화 시점의 폐기가 막았음을 보인다.
    """
    client, _, redis = env
    user_id = (await _register(client)).json()["id"]
    refresh = (await _login(client)).json()["refresh_token"]
    url = f"/api/v1/user/users/{user_id}"

    off = await client.patch(url, json={"is_active": False}, headers=admin_headers())
    on = await client.patch(url, json={"is_active": True}, headers=admin_headers())

    assert (off.status_code, on.status_code) == (200, 200)
    assert await _family_revoked(redis, refresh)
    assert (await _refresh(client, refresh)).status_code == 401


async def test_access_token_carries_the_superuser_flag(env):
    client, maker, _ = env
    await _register(client)
    plain = (await _login(client)).json()["access_token"]
    async with maker() as session:
        await session.execute(update(User).values(is_superuser=True))
        await session.commit()
    root = (await _login(client)).json()["access_token"]

    assert jwt.decode(plain, options={"verify_signature": False})["su"] is False
    assert jwt.decode(root, options={"verify_signature": False})["su"] is True
    me = await _me(client, root)
    assert me.json()["is_superuser"] is True
    listed = await client.get("/api/v1/user/users", headers={"Authorization": f"Bearer {root}"})
    assert listed.status_code == 200


async def test_every_auth_401_carries_the_bearer_challenge(env):
    """로그인·refresh·logout 의 자격 오류와 비활성 사용자의 ``/me`` 도 ``WWW-Authenticate: Bearer`` 를 싣는다.

    보호 라우트(토큰 검사)만이 아니라 이 앱이 내는 401 은 모두 같다(integration-e2e ADR-012 결정 3, F-012).
    """
    client, maker, _ = env
    await _register(client)
    access = (await _login(client)).json()["access_token"]
    async with maker() as session:
        await session.execute(update(User).values(is_active=False))
        await session.commit()

    responses = {
        "login": await _login(client, password="wrong-password"),
        "refresh": await _refresh(client, "not-a-jwt"),
        "logout": await _logout(client, "not-a-jwt"),
        "me-inactive": await _me(client, access),
    }

    assert {name: r.status_code for name, r in responses.items()} == dict.fromkeys(responses, 401)
    missing = [n for n, r in responses.items() if r.headers.get("www-authenticate") != "Bearer"]
    assert not missing, f"401 에 WWW-Authenticate: Bearer 가 없다: {missing}"


@pytest.mark.parametrize(
    ("primary_active", "replica_active", "expected"),
    [
        (True, None, 200),  # 가입 직후 — replica 에 아직 없다(복제 지연)
        (False, True, 401),  # 비활성화 직후 — replica 는 아직 활성
    ],
    ids=["registered-not-replicated", "deactivated-not-replicated"],
)
async def test_me_reads_the_user_from_primary(
    monkeypatch, primary_active, replica_active, expected
):
    """인증 사용자 조회는 replica 가 아니라 primary 에서 읽는다(integration-e2e ADR-012 결정 5, F-008).

    복제가 밀려도 유효한 토큰이 401 이 되지 않고, 비활성화는 즉시 반영된다. 라우팅 세션 팩토리를
    writer·reader 두 SQLite 로 바꿔 끼워 운영 의존성(``get_read_only_db_session``)을 그대로 탄다.
    """
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import StaticPool

    from app.core.db.router import DatabaseRouter, create_routing_sessionmaker
    from app.core.db.session import Base
    from tests.auth_headers import USER_ID, bearer

    async def engine_with(active: bool | None):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
            if active is not None:
                await conn.execute(
                    User.__table__.insert().values(
                        id=USER_ID,
                        username="lagger",
                        email="lagger@ex.com",
                        hashed_password="x",
                        is_active=active,
                        is_superuser=False,
                    )
                )
        return engine

    writer, reader = await engine_with(primary_active), await engine_with(replica_active)
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[reader]))
    monkeypatch.setattr("app.core.db.session.AsyncSessionLocal", maker)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get("/api/v1/auth/me", headers=bearer(USER_ID, "lagger"))
    finally:
        await writer.dispose()
        await reader.dispose()

    assert resp.status_code == expected, resp.text
