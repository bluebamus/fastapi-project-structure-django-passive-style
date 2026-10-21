"""관리 세션 — ``AdminSessionStore`` + ``RedisSessionMiddleware`` (admin-session-hardening ADR-001).

미들웨어를 작은 Starlette 앱에 걸고 fakeredis 위에서 HTTP 로 시험한다. 로그인 백엔드와의 결합은
``test_admin_auth.py``, 실제 조립(``create_app``)은 ``tests/core/test_admin_csrf.py`` 가 본다.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from app.core.security.admin_session import (
    SESSION_USER_KEY,
    UNAVAILABLE_MESSAGE,
    AdminSessionCookie,
    AdminSessionStore,
    RedisSessionMiddleware,
    default_admin_session_store,
)
from config import SessionSettings

SECRET = "Session-test-secret-0123456789-abcdefghij"
MAX_AGE = 8 * 60 * 60
IDLE = 30 * 60


class Clock:
    def __init__(self) -> None:
        self.now = 1_800_000_000.0

    def __call__(self) -> float:
        return self.now


def _app(store_provider) -> Starlette:
    async def login(request: Request) -> JSONResponse:
        request.session.clear()
        request.session[SESSION_USER_KEY] = request.query_params["user"]
        RedisSessionMiddleware.rotate(request.scope)
        return JSONResponse({})

    async def show(request: Request) -> JSONResponse:
        return JSONResponse(dict(request.session))

    async def put(request: Request) -> JSONResponse:
        request.session["note"] = request.query_params["v"]
        return JSONResponse({})

    async def logout(request: Request) -> JSONResponse:
        request.session.clear()
        return JSONResponse({})

    return Starlette(
        routes=[
            Route("/admin/login", login),
            Route("/admin/show", show),
            Route("/admin/put", put),
            Route("/admin/logout", logout),
        ],
        middleware=[
            Middleware(
                RedisSessionMiddleware,
                store=store_provider,
                cookie=AdminSessionCookie(https_only=False, max_age=MAX_AGE),
            )
        ],
    )


@pytest_asyncio.fixture
async def env():
    redis = FakeRedis()
    clock = Clock()
    store = AdminSessionStore(redis, SECRET, max_age=MAX_AGE, idle=IDLE, clock=clock)
    app = _app(lambda: store)
    yield app, store, redis, clock
    await redis.aclose()


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _session_keys(redis: FakeRedis) -> list[str]:
    return sorted(k.decode() for k in await redis.keys("admin:sess:*"))


# ---------------------------------------------------------------------------
# 쿠키에는 세션 ID 만, Redis 키는 HMAC
# ---------------------------------------------------------------------------
async def test_cookie_carries_only_a_random_id_and_the_redis_key_is_its_hmac(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        await client.get("/admin/login", params={"user": "u-root"})
        sid = client.cookies["admin_session"]

    assert len(sid) >= 43 and "u-root" not in sid and "." not in sid, sid
    digest = hmac.new(SECRET.encode(), sid.encode(), hashlib.sha256).hexdigest()
    assert await _session_keys(redis) == [f"admin:sess:{digest}"]
    assert not [
        k for k in await redis.keys("*") if sid.encode() in k
    ], "세션 ID 가 키에 그대로 있다"
    value = json.loads(await redis.get(f"admin:sess:{digest}"))
    assert value["data"] == {SESSION_USER_KEY: "u-root"} and value["user_id"] == "u-root"
    assert isinstance(value["created_at"], float)


async def test_cookie_attributes(env):
    app, _, _, _ = env
    async with _client(app) as client:
        header = (await client.get("/admin/login", params={"user": "u"})).headers["set-cookie"]

    lowered = header.lower()
    assert "path=/admin" in lowered and "samesite=strict" in lowered and "httponly" in lowered
    assert f"max-age={MAX_AGE}" in lowered and "secure" not in lowered


async def test_anonymous_request_that_writes_nothing_creates_nothing(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        response = await client.get("/admin/show")

    assert "set-cookie" not in response.headers
    assert await redis.keys("*") == []


# ---------------------------------------------------------------------------
# 로그아웃·회전·폐기
# ---------------------------------------------------------------------------
async def test_logout_deletes_the_key_and_a_copied_cookie_is_refused(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        await client.get("/admin/login", params={"user": "u-root"})
        copied = client.cookies["admin_session"]
        logout = await client.get("/admin/logout")
        assert "admin_session=;" in logout.headers["set-cookie"]

    assert await _session_keys(redis) == []
    assert await redis.smembers("admin:user_sessions:u-root") == set()
    async with _client(app) as attacker:
        attacker.cookies.set("admin_session", copied, domain="test.local", path="/admin")
        assert (await attacker.get("/admin/show")).json() == {}


async def test_login_rotates_the_session_id_and_deletes_the_old_key(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        await client.get("/admin/put", params={"v": "before-login"})
        before = client.cookies["admin_session"]
        old_keys = await _session_keys(redis)

        await client.get("/admin/login", params={"user": "u-root"})
        after = client.cookies["admin_session"]

        assert after != before
        assert not set(old_keys) & set(await _session_keys(redis)), "이전 키가 남았다"
        assert (await client.get("/admin/show")).json() == {SESSION_USER_KEY: "u-root"}


async def test_revoke_user_kills_every_browser_of_that_user_only(env):
    app, store, _, _ = env
    async with _client(app) as first, _client(app) as second, _client(app) as other:
        await first.get("/admin/login", params={"user": "u-root"})
        await second.get("/admin/login", params={"user": "u-root"})
        await other.get("/admin/login", params={"user": "u-other"})

        await store.revoke_user("u-root")

        assert (await first.get("/admin/show")).json() == {}
        assert (await second.get("/admin/show")).json() == {}
        assert (await other.get("/admin/show")).json() == {SESSION_USER_KEY: "u-other"}


async def test_revoke_user_without_sessions_is_a_no_op(env):
    _, store, _, _ = env
    await store.revoke_user("nobody")


# ---------------------------------------------------------------------------
# 만료
# ---------------------------------------------------------------------------
async def test_idle_ttl_is_renewed_on_every_request(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        await client.get("/admin/login", params={"user": "u-root"})
        [key] = await _session_keys(redis)
        assert await redis.ttl(key) == IDLE

        await redis.expire(key, 5)  # 거의 미사용 만료에 이른 세션
        await client.get("/admin/show")

        assert await redis.ttl(key) == IDLE, "요청이 미사용 만료를 다시 세지 않았다"


async def test_idle_expired_session_is_empty_and_its_cookie_is_cleared(env):
    app, _, redis, _ = env
    async with _client(app) as client:
        await client.get("/admin/login", params={"user": "u-root"})
        [key] = await _session_keys(redis)
        await redis.delete(key)  # Redis TTL 만료와 같다

        response = await client.get("/admin/show")

    assert response.json() == {}
    assert "admin_session=;" in response.headers["set-cookie"]


async def test_absolute_expiry_is_never_extended(env):
    app, _, redis, clock = env
    async with _client(app) as client:
        await client.get("/admin/login", params={"user": "u-root"})
        [key] = await _session_keys(redis)
        created = json.loads(await redis.get(key))["created_at"]

        clock.now += MAX_AGE - 100  # 계속 쓰는 중 — 절대 만료 100초 전
        await client.get("/admin/put", params={"v": "busy"})
        assert await redis.ttl(key) <= 100, "TTL 이 절대 만료를 넘었다"
        assert json.loads(await redis.get(key))["created_at"] == created

        clock.now += 100
        response = await client.get("/admin/show")

    assert response.json() == {}
    assert await _session_keys(redis) == []


# ---------------------------------------------------------------------------
# Redis 장애 — fail-closed
# ---------------------------------------------------------------------------
class _DownRedis:
    async def get(self, key: str) -> bytes:
        raise RedisConnectionError("down")


async def test_redis_failure_is_503_and_never_reaches_the_app():
    reached: list[bool] = []
    store = AdminSessionStore(_DownRedis(), SECRET, max_age=MAX_AGE, idle=IDLE)  # type: ignore[arg-type]
    app = _app(lambda: store)

    async def spy(request: Request) -> JSONResponse:
        reached.append(True)
        return JSONResponse({})

    app.router.routes.append(Route("/admin/spy", spy))
    async with _client(app) as client:
        client.cookies.set("admin_session", "some-sid", domain="test.local", path="/admin")
        response = await client.get("/admin/spy")

    assert response.status_code == 503
    assert response.text == UNAVAILABLE_MESSAGE
    assert reached == []


async def test_redis_failure_while_saving_before_the_response_is_503_too():
    """쿠키 없는 첫 요청이 세션에 값을 넣으면 응답 직전 저장이 Redis 장애로 실패한다 — 그것도 503 이다
    (e2e-policy-2 결정 6, integration-e2e F-009). 500·연결 끊김도, 세션 쿠키 발급도 없다.
    """
    from redis.asyncio import Redis

    # 실제 클라이언트가 닫힌 포트에 붙는다 — 쿠키가 없어 읽기는 건너뛰고 응답 직전 저장에서 처음 실패한다.
    down = Redis(host="127.0.0.1", port=1, socket_connect_timeout=1)
    store = AdminSessionStore(down, SECRET, max_age=MAX_AGE, idle=IDLE)
    transport = ASGITransport(app=_app(lambda: store), raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/admin/put", params={"v": "x"})
    finally:
        await down.aclose()

    assert response.status_code == 503
    assert response.text == UNAVAILABLE_MESSAGE
    assert "set-cookie" not in response.headers


async def test_missing_redis_client_is_503_too():
    app = _app(lambda: default_admin_session_store(None))
    async with _client(app) as client:
        response = await client.get("/admin/show")

    assert response.status_code == 503


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
def test_default_expiry_settings():
    settings = SessionSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.ADMIN_SESSION_MAX_AGE_SECONDS == 28800
    assert settings.ADMIN_SESSION_IDLE_SECONDS == 1800


@pytest.mark.parametrize(
    "values",
    [
        {"ADMIN_SESSION_MAX_AGE_SECONDS": 59},
        {"ADMIN_SESSION_IDLE_SECONDS": 59},
        {"ADMIN_SESSION_MAX_AGE_SECONDS": 600, "ADMIN_SESSION_IDLE_SECONDS": 601},
    ],
    ids=["max-too-small", "idle-too-small", "idle-longer-than-max"],
)
def test_invalid_expiry_settings_stop_startup(values):
    with pytest.raises(ValidationError):
        SessionSettings(_env_file=None, **values)  # type: ignore[call-arg]


def test_default_store_follows_the_settings(monkeypatch: pytest.MonkeyPatch):
    import config

    monkeypatch.setattr(config.session_settings, "ADMIN_SESSION_MAX_AGE_SECONDS", 3600)
    monkeypatch.setattr(config.session_settings, "ADMIN_SESSION_IDLE_SECONDS", 120)

    store = default_admin_session_store(FakeRedis())

    assert (store.max_age, store.idle) == (3600, 120)
    expected = hmac.new(
        config.session_settings.SESSION_SECRET_KEY.encode(), b"sid", hashlib.sha256
    ).hexdigest()
    assert store.key_for("sid") == f"admin:sess:{expected}"
