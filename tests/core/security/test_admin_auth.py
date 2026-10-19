"""``AdminAuthBackend`` — /admin 로그인·세션·레이트 리밋 (admin-login ADR-001·ADR-002).

실물 SQLAdmin(``Admin``)에 백엔드를 주입하고 HTTP 로 시험한다. 자격 확인은 가짜(``FakeCredentials``)
로 바꿔 백엔드의 판정만 본다 — 사용자 DB 쪽 구현은 ``app/features/auth/tests/test_admin_credentials.py``,
create_superuser 부터 이어지는 전체 흐름은 ``tests/core/test_admin_login_flow.py`` 가 본다.
레이트 리밋은 실물 ``RateLimiter`` 를 fakeredis 위에서 돌린다.
"""

from __future__ import annotations

import base64
import json
import logging

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from itsdangerous import TimestampSigner
from sqladmin import Admin
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.apps.wiring import ADMIN_TEMPLATES_DIR
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security import RateLimiter, admin_auth
from app.core.security.admin_auth import (
    CSRF_FAILED_MESSAGE,
    RATE_LIMITED_MESSAGE,
    SESSION_USER_KEY,
    AdminAuthBackend,
    AdminLoginCsrf,
    AdminLoginLimits,
    AdminSessionCookie,
)
from tests.admin_login import admin_csrf_token, admin_login

SECRET = "Pq9Rs2Tu5Vw8Xy1Za4Bc7De0Fg3Hi6Jk-admin-test"
PASSWORD = "admin-pw-123"
USER_ID = "u-root"
LIMITS = AdminLoginLimits(per_user=3, per_ip=100, window_seconds=60)


class FakeCredentials:
    """사용자명 → (id, 비밀번호). ``admins`` 에 있는 id 만 관리자다."""

    def __init__(self) -> None:
        self.users = {"root": (USER_ID, PASSWORD)}
        self.admins = {USER_ID}

    async def verify(self, username: str, password: str) -> str | None:
        found = self.users.get(username)
        if found is None or found[1] != password or found[0] not in self.admins:
            return None
        return found[0]

    async def is_admin(self, user_id: str) -> bool:
        return user_id in self.admins


def build_admin_app(
    credentials: FakeCredentials, *, https_only: bool = False, limits: AdminLoginLimits = LIMITS
) -> tuple[FastAPI, AdminAuthBackend, FakeRedis]:
    app = FastAPI()
    redis = FakeRedis()
    app.state.redis = redis
    backend = AdminAuthBackend(
        credentials=credentials,
        rate_limiter=lambda: RateLimiter(app.state.redis),
        ip_resolver=ClientIPResolver(0),
        limits=limits,
        secret_key=SECRET,
        cookie=AdminSessionCookie(https_only=https_only),
    )
    admin = Admin(
        app,
        create_async_engine("sqlite+aiosqlite:///:memory:"),
        title="Test Admin",
        authentication_backend=backend,
        templates_dir=str(ADMIN_TEMPLATES_DIR),
    )
    backend.templates = admin.templates
    return app, backend, redis


@pytest_asyncio.fixture
async def env():
    credentials = FakeCredentials()
    app, backend, redis = build_admin_app(credentials)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, credentials, redis
    await redis.aclose()


async def _login(client: AsyncClient, username: str = "root", password: str = PASSWORD):
    return await admin_login(client, username, password)


def _session(client: AsyncClient) -> dict:
    """클라이언트 쿠키 jar 의 관리 세션을 서명 검증해 읽는다."""
    raw = client.cookies.get("admin_session")
    assert raw, "관리 세션 쿠키가 없다"
    payload = TimestampSigner(SECRET).unsign(raw.encode())
    return json.loads(base64.b64decode(payload))


def _plant(client: AsyncClient, data: dict, *, secret: str = SECRET) -> None:
    """서명한 세션 쿠키를 심는다 — 서버가 내는 쿠키와 같은 domain·path 라 그것을 대체한다."""
    value = TimestampSigner(secret).sign(base64.b64encode(json.dumps(data).encode())).decode()
    client.cookies.set("admin_session", value, domain="test.local", path="/admin")


# ---------------------------------------------------------------------------
# 로그인
# ---------------------------------------------------------------------------
async def test_successful_login_redirects_to_index_and_stores_only_the_user_id(env):
    client, _, _ = env

    response = await _login(client)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/")
    assert _session(client) == {SESSION_USER_KEY: USER_ID}
    assert (await client.get("/admin/")).status_code == 200


async def test_wrong_password_and_unknown_user_get_the_same_400(env):
    client, _, _ = env

    wrong = await _login(client, password="not-the-password")
    unknown = await _login(client, username="nobody")

    assert wrong.status_code == unknown.status_code == 400
    assert wrong.text == unknown.text, "실패 사유가 응답으로 구분된다(계정 열거)"
    assert "alert alert-danger" in wrong.text
    # 세션에는 로그인 화면이 둔 CSRF 토큰만 있다 — 실패한 로그인이 사용자를 남기지 않는다.
    assert SESSION_USER_KEY not in _session(client)


async def test_non_admin_credentials_are_refused(env):
    client, credentials, _ = env
    credentials.users["bob"] = ("u-bob", PASSWORD)  # 비밀번호는 맞지만 관리자가 아니다

    response = await _login(client, username="bob")

    assert response.status_code == 400
    assert (await client.get("/admin/")).status_code == 302


async def test_rate_limit_rerenders_the_login_page_with_429_and_retry_after(env):
    client, _, _ = env
    for _ in range(LIMITS.per_user):
        await _login(client, password="wrong-password")

    response = await _login(client)  # 맞는 비밀번호여도 한도를 넘었으면 막는다

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0
    assert RATE_LIMITED_MESSAGE in response.text
    assert 'name="password"' in response.text, "로그인 화면이 다시 그려지지 않았다"


async def test_per_ip_limit_applies_across_usernames():
    app, _, redis = build_admin_app(
        FakeCredentials(), limits=AdminLoginLimits(per_user=100, per_ip=2, window_seconds=60)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        statuses = [(await _login(client, username=f"user{i}")).status_code for i in range(3)]
    await redis.aclose()

    assert statuses == [400, 400, 429]


async def test_rate_limit_keys_are_separate_from_the_api_login(env):
    client, _, redis = env
    await _login(client, password="wrong-password")

    keys = sorted(key.decode() for key in await redis.keys("*"))

    assert keys and all(key.startswith("rl:admin-login:") for key in keys), keys


async def test_success_resets_the_user_counter(env):
    client, _, redis = env
    await _login(client, password="wrong-password")
    await _login(client)

    keys = {key.decode() for key in await redis.keys("rl:admin-login:user:*")}

    assert keys == set(), "성공했는데 ip+username 카운터가 남았다"


async def test_login_logs_never_carry_the_password(env, caplog):
    client, _, _ = env
    secret_attempt = "S3cret-Attempt-Value"
    caplog.set_level(logging.INFO, logger="app.core.security.admin_auth")

    await _login(client, password=secret_attempt)
    await _login(client, username="x" * 500)
    await _login(client)

    text = "\n".join(record.getMessage() for record in caplog.records)
    assert secret_attempt not in text and PASSWORD not in text
    assert "x" * 65 not in text, "사용자명이 길이 제한 없이 로그에 남았다"
    assert "성공" in text and "실패" in text


# ---------------------------------------------------------------------------
# 세션
# ---------------------------------------------------------------------------
async def test_login_clears_values_planted_before_login(env):
    """세션 고정 방지 — 로그인 전 세션에 있던 값은 로그인 후 하나도 남지 않는다."""
    client, _, _ = env
    _plant(client, {"planted": "attacker", SESSION_USER_KEY: "u-x"})

    await _login(client)

    assert _session(client) == {SESSION_USER_KEY: USER_ID}


async def test_demotion_after_login_is_rejected_on_the_next_request(env):
    client, credentials, _ = env
    await _login(client)
    assert (await client.get("/admin/")).status_code == 200

    credentials.admins.clear()  # 강등·비활성화·삭제
    response = await client.get("/admin/")

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")
    assert "admin_session" not in client.cookies or _session(client) == {}


async def test_logout_clears_the_session(env):
    client, _, _ = env
    await _login(client)

    response = await client.get("/admin/logout")

    assert response.status_code == 302
    assert (await client.get("/admin/")).status_code == 302


async def test_session_without_a_user_id_is_not_authenticated(env):
    client, _, _ = env
    _plant(client, {SESSION_USER_KEY: 123})

    assert (await client.get("/admin/")).status_code == 302


async def test_cookie_signed_with_another_key_is_ignored(env):
    client, _, _ = env
    _plant(client, {SESSION_USER_KEY: USER_ID}, secret="another-key-another-key-another-key")

    assert (await client.get("/admin/")).status_code == 302


# ---------------------------------------------------------------------------
# 쿠키 속성
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("https_only", [False, True])
async def test_session_cookie_attributes(https_only: bool):
    app, _, redis = build_admin_app(FakeCredentials(), https_only=https_only)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await _login(client)
    await redis.aclose()

    header = response.headers["set-cookie"]
    attributes = {part.strip().split("=")[0].lower() for part in header.split(";")}
    assert header.startswith("admin_session=")
    assert "path=/admin;" in header.replace(" ", "").lower() + ";"
    assert "samesite=strict" in header.lower()
    assert "httponly" in attributes
    assert "max-age=28800" in header.lower()
    assert ("secure" in attributes) is https_only


# ---------------------------------------------------------------------------
# CSRF 토큰 (security-ops-hardening ADR-004)
# ---------------------------------------------------------------------------
class CountingCredentials(FakeCredentials):
    def __init__(self) -> None:
        super().__init__()
        self.verify_calls = 0

    async def verify(self, username: str, password: str) -> str | None:
        self.verify_calls += 1
        return await super().verify(username, password)


@pytest_asyncio.fixture
async def counting_env():
    credentials = CountingCredentials()
    app, _, redis = build_admin_app(credentials)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, credentials, redis
    await redis.aclose()


def _form(token: str | None) -> dict[str, str]:
    data = {"username": "root", "password": PASSWORD}
    if token is not None:
        data["csrf_token"] = token
    return data


async def test_login_page_renders_the_session_token_as_a_hidden_field(env):
    client, _, _ = env

    token = await admin_csrf_token(client)

    assert len(token) >= 43, "secrets.token_urlsafe(32) 보다 짧다"
    assert _session(client)[AdminLoginCsrf.SESSION_KEY] == token
    assert await admin_csrf_token(client) == token, "같은 세션에서는 토큰이 유지돼야 한다"


@pytest.mark.parametrize("token", [None, "", "forged-token-value"])
async def test_post_without_a_valid_token_is_403_before_credentials_and_rate_limit(
    counting_env, token
):
    client, credentials, redis = counting_env
    await admin_csrf_token(client)  # 세션에는 진짜 토큰이 있다

    response = await client.post("/admin/login", data=_form(token))

    assert response.status_code == 403
    assert CSRF_FAILED_MESSAGE in response.text
    assert 'name="password"' in response.text, "로그인 화면이 다시 그려지지 않았다"
    assert credentials.verify_calls == 0, "CSRF 실패인데 자격 확인을 했다"
    assert await redis.keys("*") == [], "CSRF 실패가 레이트 리밋 카운터를 올렸다"
    assert SESSION_USER_KEY not in _session(client)


async def test_post_without_any_session_is_403(counting_env):
    client, credentials, _ = counting_env

    response = await client.post("/admin/login", data=_form("anything"))

    assert response.status_code == 403
    assert credentials.verify_calls == 0


async def test_valid_token_proceeds_to_the_existing_flow(counting_env):
    client, credentials, _ = counting_env
    token = await admin_csrf_token(client)

    response = await client.post("/admin/login", data=_form(token))

    assert response.status_code == 302
    assert credentials.verify_calls == 1


async def test_token_from_another_session_is_rejected(counting_env):
    client, credentials, _ = counting_env
    app = client._transport.app  # type: ignore[attr-defined]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        stolen = await admin_csrf_token(other)
    await admin_csrf_token(client)  # 피해자 세션에는 자기 토큰이 있다

    response = await client.post("/admin/login", data=_form(stolen))

    assert response.status_code == 403
    assert credentials.verify_calls == 0


async def test_token_rotates_after_a_successful_login(env):
    client, _, _ = env
    before = await admin_csrf_token(client)

    assert (await client.post("/admin/login", data=_form(before))).status_code == 302
    assert AdminLoginCsrf.SESSION_KEY not in _session(client), "로그인 후에도 옛 토큰이 남았다"
    after = await admin_csrf_token(client)

    assert after != before


async def test_failed_login_keeps_the_token_so_the_user_can_retry(env):
    client, _, _ = env
    token = await admin_csrf_token(client)

    failed = await client.post("/admin/login", data={**_form(token), "password": "wrong-pw"})
    forged = await client.post("/admin/login", data=_form("forged"))

    assert failed.status_code == 400 and forged.status_code == 403
    for page in (failed, forged):
        assert f'name="csrf_token" value="{token}"' in page.text
    assert (await client.post("/admin/login", data=_form(token))).status_code == 302


async def test_token_comparison_uses_a_constant_time_function(env, monkeypatch):
    client, _, _ = env
    calls: list[tuple[bytes, bytes]] = []
    real = admin_auth.hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr(admin_auth.hmac, "compare_digest", spy)
    token = await admin_csrf_token(client)

    await client.post("/admin/login", data=_form(token))

    # itsdangerous 도 서명 검증에 같은 함수를 쓴다 — 토큰 쌍이 그 안에 있는지만 본다.
    assert (token.encode(), token.encode()) in calls
