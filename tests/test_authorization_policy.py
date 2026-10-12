"""인가 정책 표 — 모든 오퍼레이션의 접근 등급을 한 곳에 고정한다 (service-hardening F2).

등급:

* ``public`` — 토큰 없이 쓴다.
* ``auth``   — 인증만 필요하다(``CurrentPrincipal``).
* ``owner``  — 인증 + 소유자 또는 슈퍼유저(``OwnershipPolicy`` — 판정은 서비스 안).
* ``self``   — 인증 + 본인 또는 슈퍼유저(user 단건 조회·수정).
* ``admin``  — 슈퍼유저만(``require_superuser``).

표가 OpenAPI 와 어긋나면 실패한다 — 새 라우트는 등급을 정해 이 표에 올려야 한다. 표의
등급은 OpenAPI 의 ``security`` 와 교차 확인하고(공개 ⇔ security 없음), 실제 요청으로
토큰 없음 → 401, 일반 사용자 → 관리자 경로 403 을 오퍼레이션마다 확인한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middlewares.access_log_sink import get_access_log_sink, set_access_log_sink
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.middlewares.user_info_middleware import UserInfoMiddleware
from app.core.redis import get_redis
from app.core.security.dependencies import CurrentPrincipal, get_token_service
from config import jwt_settings
from main import app
from tests.auth_headers import USER_ID, user_headers
from tests.session_overrides import sqlite_session_overrides

POLICY: dict[tuple[str, str], str] = {
    ("GET", "/health"): "public",
    ("GET", "/ready"): "public",
    # auth
    ("POST", "/api/v1/auth/register"): "public",
    ("POST", "/api/v1/auth/login"): "public",
    ("POST", "/api/v1/auth/refresh"): "public",
    ("POST", "/api/v1/auth/logout"): "public",
    ("GET", "/api/v1/auth/me"): "auth",
    # blog / sns / reply
    ("GET", "/api/v1/blog/posts"): "public",
    ("POST", "/api/v1/blog/posts"): "auth",
    ("GET", "/api/v1/blog/posts/{post_id}"): "public",
    ("PATCH", "/api/v1/blog/posts/{post_id}"): "owner",
    ("DELETE", "/api/v1/blog/posts/{post_id}"): "owner",
    ("GET", "/api/v1/sns/posts"): "public",
    ("POST", "/api/v1/sns/posts"): "auth",
    ("GET", "/api/v1/sns/posts/{post_id}"): "public",
    ("PATCH", "/api/v1/sns/posts/{post_id}"): "owner",
    ("DELETE", "/api/v1/sns/posts/{post_id}"): "owner",
    ("GET", "/api/v1/reply/replies"): "public",
    ("POST", "/api/v1/reply/replies"): "auth",
    ("GET", "/api/v1/reply/replies/{reply_id}"): "public",
    ("PATCH", "/api/v1/reply/replies/{reply_id}"): "owner",
    ("DELETE", "/api/v1/reply/replies/{reply_id}"): "owner",
    # user
    ("GET", "/api/v1/user/users"): "admin",
    ("POST", "/api/v1/user/users"): "admin",
    ("GET", "/api/v1/user/users/{user_id}"): "self",
    ("PATCH", "/api/v1/user/users/{user_id}"): "self",
    ("DELETE", "/api/v1/user/users/{user_id}"): "admin",
    # catalog
    ("GET", "/api/v1/catalog/products"): "public",
    ("POST", "/api/v1/catalog/products"): "admin",
    ("GET", "/api/v1/catalog/products/{product_id}"): "public",
    ("PATCH", "/api/v1/catalog/products/{product_id}"): "admin",
    ("DELETE", "/api/v1/catalog/products/{product_id}"): "admin",
    # reports · home 접속 로그
    ("GET", "/api/v1/reports/daily-sales"): "admin",
    ("GET", "/api/v1/home/access-logs"): "admin",
    ("GET", "/api/v1/home/access-logs/recent"): "admin",
    ("GET", "/api/v1/home/access-logs/by-ip/{ip_address}"): "admin",
    ("GET", "/api/v1/home/access-logs/by-user/{user_id}"): "admin",
    ("GET", "/api/v1/home/access-logs/stats"): "admin",
}

PROTECTED = sorted(key for key, level in POLICY.items() if level != "public")
ADMIN_ONLY = sorted(key for key, level in POLICY.items() if level == "admin")
PUBLIC_READS = sorted(
    key
    for key, level in POLICY.items()
    if level == "public" and key[1].startswith("/api/v1/") and key[0] == "GET"
)

#: 경로 파라미터 자리에 넣는 값(존재하지 않는 리소스 — 인가가 먼저 막는지 본다).
_PARAMS = {
    "post_id": "x",
    "reply_id": "x",
    "user_id": "x",
    "product_id": "x",
    "ip_address": "1.2.3.4",
}
#: 쿼리가 필수인 경로.
_QUERY = {"/api/v1/reports/daily-sales": {"start_date": "2026-01-01", "end_date": "2026-01-02"}}


def _url(path: str) -> str:
    return path.format(**_PARAMS)


def _operations() -> dict[tuple[str, str], dict[str, Any]]:
    spec = app.openapi()
    return {
        (method.upper(), path): operation
        for path, item in spec["paths"].items()
        for method, operation in item.items()
    }


# ---------------------------------------------------------------------------
# 표 ↔ OpenAPI
# ---------------------------------------------------------------------------
def test_policy_table_covers_every_operation():
    """새 오퍼레이션은 등급을 정해 표에 올려야 한다(빠지거나 남은 항목이 없다)."""
    assert set(_operations()) == set(POLICY)


def test_policy_table_matches_openapi_security():
    """공개 ⇔ security 없음. 보호 오퍼레이션은 Bearer 스킴을 선언하고 401 을 문서화한다."""
    mismatched = []
    for key, operation in _operations().items():
        secured = bool(operation.get("security"))
        if secured != (POLICY[key] != "public"):
            mismatched.append((key, POLICY[key], secured))
        if secured and "401" not in operation["responses"]:
            mismatched.append((key, "401 미문서화", secured))
        if POLICY[key] in {"owner", "self", "admin"} and "403" not in operation["responses"]:
            mismatched.append((key, "403 미문서화", secured))
    assert not mismatched


# ---------------------------------------------------------------------------
# 요청으로 확인
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client():
    async with sqlite_session_overrides(app):
        redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: redis
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def _call(client: AsyncClient, key: tuple[str, str], **kwargs: Any):
    method, path = key
    if method in {"POST", "PATCH"}:
        kwargs.setdefault("json", {})
    return await client.request(method, _url(path), params=_QUERY.get(path), **kwargs)


@pytest.mark.parametrize("key", PROTECTED, ids=lambda k: f"{k[0]} {k[1]}")
async def test_protected_operation_without_token_is_401(client, key):
    resp = await _call(client, key)

    assert resp.status_code == 401, resp.text
    assert resp.json()["error_code"] == "UNAUTHORIZED"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("key", ADMIN_ONLY, ids=lambda k: f"{k[0]} {k[1]}")
async def test_admin_operation_rejects_a_normal_user(client, key):
    resp = await _call(client, key, headers=user_headers())

    assert resp.status_code == 403, resp.text
    assert resp.json()["error_code"] == "FORBIDDEN"


@pytest.mark.parametrize("key", PUBLIC_READS, ids=lambda k: f"{k[0]} {k[1]}")
async def test_public_read_needs_no_token(client, key):
    resp = await _call(client, key)

    assert resp.status_code in {200, 404}, resp.text


# ---------------------------------------------------------------------------
# 401 — 토큰 종류별
# ---------------------------------------------------------------------------
def _access_claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": USER_ID,
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "j" * 32,
        "iss": jwt_settings.JWT_ISSUER,
        "aud": jwt_settings.JWT_AUDIENCE,
        "username": "alice",
        "su": False,
        **overrides,
    }
    return {k: v for k, v in claims.items() if v is not None}


def _sign(claims: dict[str, Any], key: str | None = None) -> str:
    return jwt.encode(
        claims,
        key or jwt_settings.ACCESS_TOKEN_SECRET_KEY,
        algorithm=jwt_settings.JWT_ALGORITHM,
    )


_PAST = datetime.now(UTC) - timedelta(hours=1)

BAD_TOKENS = {
    "expired": lambda: _sign(_access_claims(iat=_PAST, nbf=_PAST, exp=_PAST)),
    "forged": lambda: _sign(_access_claims(), key="not-the-server-key-" + "0" * 48),
    "su-missing": lambda: _sign(_access_claims(su=None)),
    "su-not-bool": lambda: _sign(_access_claims(su="true")),
    "refresh-as-access": lambda: get_token_service().issue_refresh(USER_ID, "fam").token,
    "garbage": lambda: "not-a-jwt",
}


@pytest.mark.parametrize("name", sorted(BAD_TOKENS))
async def test_bad_token_is_401(client, name):
    token = BAD_TOKENS[name]()

    resp = await client.post(
        "/api/v1/blog/posts",
        json={"title": "t", "content": "c"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 401
    assert resp.json()["error_code"] == "AUTH_INVALID_TOKEN"


async def test_normal_user_token_claiming_superuser_needs_the_server_key(client):
    """``su`` 를 true 로 바꿔 다시 서명하려면 서버 키가 필요하다 — 다른 키면 401."""
    forged = _sign(_access_claims(su=True), key="attacker-key-" + "1" * 48)

    resp = await client.get("/api/v1/user/users", headers={"Authorization": f"Bearer {forged}"})

    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 접속 로그 user_id (ledger F-024)
# ---------------------------------------------------------------------------
class _RecordingSink:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save(self, data: dict) -> None:
        self.saved.append(data)


async def test_authenticated_request_records_user_id_in_access_log():
    """인증 의존성이 핸들러 실행 중에 채운 ``request.state.user_id`` 를 미들웨어가 응답 뒤에 읽는다."""
    probe = FastAPI()
    probe.add_middleware(UserInfoMiddleware, ip_resolver=ClientIPResolver(0))

    @probe.get("/whoami")
    async def whoami(principal: CurrentPrincipal) -> dict:
        return {"id": principal.id}

    @probe.get("/anonymous")
    async def anonymous() -> dict:
        return {}

    original = get_access_log_sink()
    sink = _RecordingSink()
    set_access_log_sink(sink)
    try:
        transport = ASGITransport(app=probe)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            assert (await c.get("/whoami", headers=user_headers())).status_code == 200
            await c.get("/anonymous")
        await access_log_tasks.drain(timeout=2)
    finally:
        set_access_log_sink(original)

    recorded = {entry["request_path"]: entry["user_id"] for entry in sink.saved}
    assert recorded == {"/whoami": USER_ID, "/anonymous": None}
