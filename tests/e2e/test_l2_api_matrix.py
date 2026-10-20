"""L2 — API operation 전수 매트릭스 (정상·검증 오류·미인증·권한 부족·없음·잘못된 메서드·접근 정책).

operation 마다 칸을 채운다. 해당하지 않는 칸은 ``test_zz_inventory.py`` 의 ``NOT_APPLICABLE`` 에
사유와 함께 적는다(빈 칸 금지). 요청은 실제 uvicorn(ENV=production) → MySQL primary/replica·Redis 로 간다.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import cache
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    BASE_URL,
    USER_PASSWORD,
    Stack,
    bearer,
    login,
    register_and_login,
    unique,
)
from tests.e2e.ledger import OBSERVATIONS, covers
from tests.e2e.openapi_check import operations, path_methods, response_errors

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(300)]


@cache
def access_levels() -> dict[str, str]:
    """operationId → 선언된 접근 수준(``AccessPolicyGuard`` 가 기동 때 보는 그 판정)."""
    from app.core.security.access import AccessPolicyGuard
    from main import app

    by_route = AccessPolicyGuard().levels(app)
    return {
        op: next(iter(by_route[(method, path)])).value
        for op, (method, path) in operations().items()
    }


@dataclass
class World:
    """매트릭스가 쓰는 사용자와 자원을 만드는 도구."""

    client: httpx.Client
    stack: Stack
    a: dict[str, str]
    b: dict[str, str]
    s: dict[str, str]
    made: list[str] = field(default_factory=list)

    def as_(self, who: dict[str, str] | None) -> dict[str, str]:
        return bearer(who["access"]) if who else {}

    def post(self, owner: dict[str, str]) -> str:
        r = self.client.post(
            "/api/v1/blog/posts", json={"title": "글", "content": "본문"}, headers=self.as_(owner)
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def reply(self, owner: dict[str, str]) -> str:
        r = self.client.post(
            "/api/v1/reply/replies",
            json={"content": "댓글", "post_id": self.post(owner)},
            headers=self.as_(owner),
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def sns(self, owner: dict[str, str]) -> str:
        r = self.client.post("/api/v1/sns/posts", json={"content": "피드"}, headers=self.as_(owner))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def product(self) -> str:
        body = {"sku": unique("SKU"), "name": "상품", "price": "10.00", "stock": 3}
        r = self.client.post("/api/v1/catalog/products", json=body, headers=self.as_(self.s))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def user(self) -> str:
        name = unique("made")
        body = {"username": name, "email": f"{name}@example.com", "password": USER_PASSWORD}
        r = self.client.post("/api/v1/user/users", json=body, headers=self.as_(self.s))
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def fresh_refresh(self, who: dict[str, str]) -> str:
        return login(self.client, who["username"])["refresh"]


@dataclass
class Req:
    path: str
    json: Any = None
    data: Any = None
    params: dict[str, Any] | None = None


#: operationId → (World, 자원 소유자) → 유효한 요청. 소유자의 자원을 그때그때 새로 만든다.
REQUESTS: dict[str, Callable[[World, dict[str, str]], Req]] = {
    "getAccessLogs": lambda w, o: Req("/api/v1/home/access-logs", params={"limit": 5}),
    "getRecentAccessLogs": lambda w, o: Req("/api/v1/home/access-logs/recent", params={"limit": 5}),
    "getAccessLogsByIp": lambda w, o: Req("/api/v1/home/access-logs/by-ip/127.0.0.1"),
    "getAccessLogsByUser": lambda w, o: Req(f"/api/v1/home/access-logs/by-user/{w.a['id']}"),
    "getAccessLogStats": lambda w, o: Req("/api/v1/home/access-logs/stats"),
    "createPost": lambda w, o: Req(
        "/api/v1/blog/posts", json={"title": "새 글", "content": "본문"}
    ),
    "listPosts": lambda w, o: Req("/api/v1/blog/posts", params={"limit": 5}),
    "getPost": lambda w, o: Req(f"/api/v1/blog/posts/{w.post(o)}"),
    "updatePost": lambda w, o: Req(f"/api/v1/blog/posts/{w.post(o)}", json={"title": "수정됨"}),
    "deletePost": lambda w, o: Req(f"/api/v1/blog/posts/{w.post(o)}"),
    "createReply": lambda w, o: Req(
        "/api/v1/reply/replies", json={"content": "새 댓글", "post_id": w.post(o)}
    ),
    "listReplies": lambda w, o: Req("/api/v1/reply/replies", params={"limit": 5}),
    "getReply": lambda w, o: Req(f"/api/v1/reply/replies/{w.reply(o)}"),
    "updateReply": lambda w, o: Req(
        f"/api/v1/reply/replies/{w.reply(o)}", json={"content": "수정됨"}
    ),
    "deleteReply": lambda w, o: Req(f"/api/v1/reply/replies/{w.reply(o)}"),
    "createSnsPost": lambda w, o: Req("/api/v1/sns/posts", json={"content": "새 피드"}),
    "listSnsPosts": lambda w, o: Req("/api/v1/sns/posts", params={"limit": 5}),
    "getSnsPost": lambda w, o: Req(f"/api/v1/sns/posts/{w.sns(o)}"),
    "updateSnsPost": lambda w, o: Req(f"/api/v1/sns/posts/{w.sns(o)}", json={"content": "수정됨"}),
    "deleteSnsPost": lambda w, o: Req(f"/api/v1/sns/posts/{w.sns(o)}"),
    "createUser": lambda w, o: Req(
        "/api/v1/user/users",
        json={
            "username": (n := unique("new")),
            "email": f"{n}@example.com",
            "password": USER_PASSWORD,
        },
    ),
    "listUsers": lambda w, o: Req("/api/v1/user/users", params={"limit": 5}),
    "getUser": lambda w, o: Req(f"/api/v1/user/users/{o['id']}"),
    "updateUser": lambda w, o: Req(
        f"/api/v1/user/users/{o['id']}", json={"email": f"{unique('m')}@example.com"}
    ),
    "deleteUser": lambda w, o: Req(f"/api/v1/user/users/{w.user()}"),
    "authRegister": lambda w, o: Req(
        "/api/v1/auth/register",
        json={
            "username": (n := unique("reg")),
            "email": f"{n}@example.com",
            "password": USER_PASSWORD,
        },
    ),
    "authLogin": lambda w, o: Req(
        "/api/v1/auth/login", data={"username": o["username"], "password": USER_PASSWORD}
    ),
    "authRefresh": lambda w, o: Req(
        "/api/v1/auth/refresh", json={"refresh_token": w.fresh_refresh(o)}
    ),
    "authLogout": lambda w, o: Req(
        "/api/v1/auth/logout", json={"refresh_token": w.fresh_refresh(o)}
    ),
    "authMe": lambda w, o: Req("/api/v1/auth/me"),
    "createProduct": lambda w, o: Req(
        "/api/v1/catalog/products",
        json={"sku": unique("SKU"), "name": "상품", "price": "1.50", "stock": 1},
    ),
    "listProducts": lambda w, o: Req("/api/v1/catalog/products", params={"active_only": "true"}),
    "getProduct": lambda w, o: Req(f"/api/v1/catalog/products/{w.product()}"),
    "updateProduct": lambda w, o: Req(
        f"/api/v1/catalog/products/{w.product()}", json={"price": "9.99"}
    ),
    "deleteProduct": lambda w, o: Req(f"/api/v1/catalog/products/{w.product()}"),
    "getDailySalesReport": lambda w, o: Req(
        "/api/v1/reports/daily-sales", params={"start_date": "2026-01-01", "end_date": "2026-01-07"}
    ),
    "healthCheck": lambda w, o: Req("/health"),
    "readinessCheck": lambda w, o: Req("/ready"),
}

#: 쓰기 operation 의 DB 반영 확인 — (primary 에서 본다).
TABLES = {
    "Post": "blog_posts",
    "Reply": "replies",
    "SnsPost": "sns_posts",
    "Product": "catalog_products",
    "User": "users",
}


def send(
    w: World, op: str, who: dict[str, str] | None, req: Req, method: str | None = None
) -> httpx.Response:
    verb = method or operations()[op][0]
    return w.client.request(
        verb, req.path, json=req.json, data=req.data, params=req.params, headers=w.as_(who)
    )


def success_status(op: str) -> int:
    method, path = operations()[op]
    from tests.e2e.openapi_check import spec

    return min(
        int(code)
        for code in spec()["paths"][path][method.lower()]["responses"]
        if code.startswith("2")
    )


def actor(w: World, op: str) -> dict[str, str] | None:
    """정상 호출의 주체 — 선언된 접근 수준 그대로."""
    return {"public": None, "public_write": None, "login": w.a, "superuser": w.s}[
        access_levels()[op]
    ]


@pytest.fixture(scope="module")
def world(stack: Stack, superuser) -> World:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        w = World(client, stack, register_and_login(client), register_and_login(client), superuser)
        yield w


ALL_OPS = sorted(REQUESTS)


def test_request_table_covers_every_operation():
    assert set(REQUESTS) == set(operations()), "REQUESTS 와 실제 operation 이 다르다"


@pytest.mark.parametrize("op", ALL_OPS)
def test_success_matches_openapi_and_persists(world: World, op: str):
    who = actor(world, op)
    owner = who or world.a
    req = REQUESTS[op](world, owner)
    response = send(world, op, who, req)
    expected = success_status(op)
    assert response.status_code == expected, f"{op}: {response.status_code} {response.text[:500]}"
    body = response.json() if response.content else None
    assert not response_errors(op, expected, body), response_errors(op, expected, body)
    _check_persisted(world, op, req, body)
    covers(f"op:{op}", "정상")


def _check_persisted(w: World, op: str, req: Req, body: Any) -> None:
    """쓰기 결과가 DB·Redis 에 실제로 남았는지 primary 에서 본다."""
    for suffix, table in TABLES.items():
        if op == f"create{suffix}":
            assert w.stack.sql(f"SELECT 1 FROM {table} WHERE id=%s", body["id"]), op  # noqa: S608
        if op == f"delete{suffix}":
            ident = req.path.rsplit("/", 1)[-1]
            assert not w.stack.sql(f"SELECT 1 FROM {table} WHERE id=%s", ident), op  # noqa: S608
        if op == f"update{suffix}":
            ident = req.path.rsplit("/", 1)[-1]
            column, value = next(iter(req.json.items()))
            row = w.stack.sql(f"SELECT {column} AS v FROM {table} WHERE id=%s", ident)[0]  # noqa: S608
            assert str(row["v"]) == str(value), (op, row, value)
    if op == "authRegister":
        assert w.stack.sql("SELECT 1 FROM users WHERE username=%s", req.json["username"])
    if op in ("authLogin", "authRefresh"):
        jti_keys = list(w.stack.redis().scan_iter("auth:rt:*", count=1000))
        assert jti_keys, f"{op}: refresh 회전 기록(auth:rt:*)이 없다"
    if op == "authLogout":
        import jwt

        fam = jwt.decode(req.json["refresh_token"], options={"verify_signature": False})["fam"]
        assert w.stack.redis().exists(
            f"auth:fam:{fam}:revoked"
        ), "logout 이 family 를 폐기하지 않았다"


# ── 미인증 ────────────────────────────────────────────────────────────────
PROTECTED = [op for op in ALL_OPS if access_levels()[op] in ("login", "superuser")]


@pytest.mark.parametrize("op", PROTECTED)
@pytest.mark.parametrize("token", [None, "not-a-jwt"], ids=["no-header", "bad-token"])
def test_protected_operations_reject_anonymous_with_bearer_challenge(world: World, op: str, token):
    req = REQUESTS[op](world, world.a)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    response = world.client.request(
        operations()[op][0], req.path, json=req.json, params=req.params, headers=headers
    )
    assert response.status_code == 401, f"{op}: {response.status_code}"
    assert response.headers.get("www-authenticate") == "Bearer", f"{op}: {dict(response.headers)}"
    assert response.json()["error_code"] in ("UNAUTHORIZED", "AUTH_INVALID_TOKEN")
    covers(f"op:{op}", "미인증")


def test_public_write_auth_operations_reject_bad_credentials(world: World):
    """PublicWrite 인 로그인·refresh·logout 의 "미인증" 은 자격(비밀번호·refresh 토큰)이 틀린 경우다."""
    wrong = world.client.post(
        "/api/v1/auth/login", data={"username": world.a["username"], "password": "x" * 12}
    )
    assert wrong.status_code == 401
    covers("op:authLogin", "미인증")
    responses = {"authLogin": wrong}
    for op in ("authRefresh", "authLogout"):
        bad = world.client.post(operations()[op][1], json={"refresh_token": "not-a-jwt"})
        assert bad.status_code == 401, (op, bad.status_code, bad.text)
        assert bad.json()["error_code"] == "AUTH_INVALID_TOKEN"
        responses[op] = bad
        covers(f"op:{op}", "미인증")
    missing = sorted(op for op, r in responses.items() if "www-authenticate" not in r.headers)
    if missing:
        OBSERVATIONS.add(
            f"PublicWrite 인증 operation 의 401 에는 WWW-Authenticate 가 없다({', '.join(missing)}) — "
            "보호 라우트(Bearer 검사)는 붙는다. 로그인·refresh 의 자격 오류에 도전 헤더를 붙일지는 정책 결정"
        )


# ── 권한 부족 ─────────────────────────────────────────────────────────────
SUPER_ONLY = [op for op in ALL_OPS if access_levels()[op] == "superuser"]
#: 로그인 사용자의 소유권 검사 대상 — 남(B)의 자원을 A 가 건드린다.
OWNERSHIP = [
    "updatePost",
    "deletePost",
    "updateReply",
    "deleteReply",
    "updateSnsPost",
    "deleteSnsPost",
    "getUser",
    "updateUser",
]


@pytest.mark.parametrize("op", SUPER_ONLY)
def test_superuser_operations_forbid_regular_user(world: World, op: str):
    response = send(world, op, world.a, REQUESTS[op](world, world.a))
    assert response.status_code == 403, f"{op}: {response.status_code}"
    assert response.json()["error_code"] == "FORBIDDEN"
    covers(f"op:{op}", "권한부족")


@pytest.mark.parametrize("op", OWNERSHIP)
def test_ownership_forbids_other_users_resources(world: World, op: str):
    req = REQUESTS[op](world, world.b)
    response = send(world, op, world.a, req)
    assert response.status_code == 403, f"{op}: {response.status_code} {response.text[:300]}"
    covers(f"op:{op}", "권한부족")


def test_regular_user_cannot_grant_privileged_fields_to_self(world: World):
    response = world.client.patch(
        f"/api/v1/user/users/{world.a['id']}",
        json={"is_superuser": True},
        headers=world.as_(world.a),
    )
    assert response.status_code == 403
    assert (
        world.stack.sql("SELECT is_superuser FROM users WHERE id=%s", world.a["id"])[0][
            "is_superuser"
        ]
        == 0
    )


# ── 없음 ──────────────────────────────────────────────────────────────────
WITH_ID = [op for op in ALL_OPS if "{" in operations()[op][1] and "by-" not in operations()[op][1]]


@pytest.mark.parametrize("op", WITH_ID)
@pytest.mark.parametrize("ident", ["uuid", "not-a-uuid"])
def test_missing_resource_is_404(world: World, op: str, ident: str):
    missing = str(uuid.uuid4()) if ident == "uuid" else "not-a-uuid"
    method, template = operations()[op]
    path = template.split("{", 1)[0] + missing
    req = REQUESTS[op](world, world.a)
    who = world.s if access_levels()[op] != "public" else None
    response = world.client.request(method, path, json=req.json, headers=world.as_(who))
    assert response.status_code == 404, f"{op}: {response.status_code} {response.text[:300]}"
    assert response.json()["error_code"].endswith("NOT_FOUND")
    covers(f"op:{op}", "없음")


@pytest.mark.parametrize("op", ["getAccessLogsByIp", "getAccessLogsByUser"])
def test_lookup_by_unknown_key_is_an_empty_list(world: World, op: str):
    method, template = operations()[op]
    path = template.split("{", 1)[0] + (
        "203.0.113.250" if "ip" in op.lower() else str(uuid.uuid4())
    )
    response = world.client.request(method, path, headers=world.as_(world.s))
    assert response.status_code == 200
    assert response.json() == []
    covers(f"op:{op}", "없음")


# ── 검증 오류 ─────────────────────────────────────────────────────────────
INVALID: dict[str, Callable[[World], Req]] = {
    "getAccessLogs": lambda w: Req("/api/v1/home/access-logs", params={"limit": 0}),
    "getRecentAccessLogs": lambda w: Req("/api/v1/home/access-logs/recent", params={"limit": 101}),
    "getAccessLogsByIp": lambda w: Req(
        "/api/v1/home/access-logs/by-ip/127.0.0.1", params={"skip": -1}
    ),
    "getAccessLogsByUser": lambda w: Req(
        f"/api/v1/home/access-logs/by-user/{w.a['id']}", params={"limit": "x"}
    ),
    "createPost": lambda w: Req("/api/v1/blog/posts", json={"title": "", "content": "x"}),
    "listPosts": lambda w: Req("/api/v1/blog/posts", params={"limit": 0}),
    "updatePost": lambda w: Req(f"/api/v1/blog/posts/{w.post(w.a)}", json={"title": "x" * 201}),
    "createReply": lambda w: Req("/api/v1/reply/replies", json={}),
    "listReplies": lambda w: Req("/api/v1/reply/replies", params={"skip": -1}),
    "updateReply": lambda w: Req(f"/api/v1/reply/replies/{w.reply(w.a)}", json={"content": 123}),
    "createSnsPost": lambda w: Req("/api/v1/sns/posts", json={"content": "x" * 501}),
    "listSnsPosts": lambda w: Req("/api/v1/sns/posts", params={"limit": 1000}),
    "updateSnsPost": lambda w: Req(f"/api/v1/sns/posts/{w.sns(w.a)}", json={"content": ["x"]}),
    "createUser": lambda w: Req(
        "/api/v1/user/users", json={"username": "u", "email": "bad", "password": "short"}
    ),
    "listUsers": lambda w: Req("/api/v1/user/users", params={"limit": 0}),
    "updateUser": lambda w: Req(f"/api/v1/user/users/{w.a['id']}", json={"email": "not-an-email"}),
    "authRegister": lambda w: Req(
        "/api/v1/auth/register", json={"username": "x", "email": "x", "password": "1"}
    ),
    "authLogin": lambda w: Req("/api/v1/auth/login", data={"username": "only"}),
    "authRefresh": lambda w: Req("/api/v1/auth/refresh", json={}),
    "authLogout": lambda w: Req("/api/v1/auth/logout", json={"refresh_token": "x" * 4097}),
    "createProduct": lambda w: Req(
        "/api/v1/catalog/products", json={"sku": "S", "name": "n", "price": "-1"}
    ),
    "listProducts": lambda w: Req("/api/v1/catalog/products", params={"active_only": "maybe"}),
    "updateProduct": lambda w: Req(
        f"/api/v1/catalog/products/{w.product()}", json={"stock": "many"}
    ),
    "getDailySalesReport": lambda w: Req(
        "/api/v1/reports/daily-sales", params={"start_date": "2026-02-30", "end_date": "2026-03-01"}
    ),
}


@pytest.mark.parametrize("op", sorted(INVALID))
def test_invalid_input_is_422_in_the_project_error_format(world: World, op: str):
    req = INVALID[op](world)
    who = actor(world, op) or None
    response = send(world, op, who, req)
    assert response.status_code == 422, f"{op}: {response.status_code} {response.text[:300]}"
    body = response.json()
    assert body["error_code"] == "VALIDATION_ERROR", body
    assert body["detail"] and {"field", "message", "type"} <= set(body["detail"][0]), body
    mismatch = response_errors(op, 422, body)
    if mismatch:
        OBSERVATIONS.add(
            "422 응답 형식이 OpenAPI 광고(HTTPValidationError: detail[loc,msg,type])와 다르다 — 실제는 "
            "ErrorResponse(error_code·message·detail[field,message,type])"
        )
    covers(f"op:{op}", "검증오류")


def test_report_range_rules_are_422(world: World):
    for params in (
        {"start_date": "2026-03-02", "end_date": "2026-03-01"},
        {"start_date": "2025-01-01", "end_date": "2026-03-01"},
    ):
        response = world.client.get(
            "/api/v1/reports/daily-sales", params=params, headers=world.as_(world.s)
        )
        assert response.status_code == 422, (params, response.text)
        assert response.json()["error_code"] == "REPORTS_INVALID_DATE_RANGE"


# ── 잘못된 메서드 ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("op", ALL_OPS)
def test_wrong_method_is_405_with_allow(world: World, op: str):
    method, template = operations()[op]
    path = template.replace("{ip_address}", "127.0.0.1")
    path = path.split("{", 1)[0] + str(uuid.uuid4()) if "{" in path else path
    response = world.client.request("PUT", path, headers=world.as_(world.s))
    assert response.status_code == 405, f"{op}: {response.status_code}"
    allowed = {m.strip() for m in response.headers["allow"].split(",")}
    # 같은 경로에 메서드별 라우트가 여럿이면 Starlette 는 **처음 맞은 라우트의** 메서드만 Allow 에
    # 싣는다. 메서드 분할 경로는 현행 유지(사용자 결정) — 값만 기록한다.
    assert allowed and allowed <= path_methods(template) | {"HEAD"} and "PUT" not in allowed, (
        op,
        allowed,
    )
    if not path_methods(template) <= allowed:
        OBSERVATIONS.add(
            "405 Allow 가 경로의 메서드 일부만 싣는다(메서드 분할 경로 — 예: /api/v1/blog/posts 는 "
            "Allow: POST, /api/v1/blog/posts/{id} 는 Allow: GET). 현행 유지 결정 — 값만 기록"
        )
    covers(f"op:{op}", "잘못된메서드")


# ── 접근 정책 대조 ────────────────────────────────────────────────────────
@pytest.mark.parametrize("op", ALL_OPS)
def test_declared_access_level_matches_real_responses(world: World, op: str):
    level = access_levels()[op]
    anonymous = send(world, op, None, REQUESTS[op](world, world.a)).status_code
    regular = send(world, op, world.a, REQUESTS[op](world, world.a)).status_code
    if level in ("public", "public_write"):
        assert 200 <= anonymous < 300, f"{op}({level}) 익명 {anonymous}"
    else:
        assert anonymous == 401, f"{op}({level}) 익명 {anonymous}"
    if level == "superuser":
        assert regular == 403, f"{op}({level}) 일반 사용자 {regular}"
    else:
        assert 200 <= regular < 300, f"{op}({level}) 일반 사용자 {regular}"
    covers(f"op:{op}", "접근정책")


def test_daily_sales_report_sums_paid_orders_by_local_business_day(world: World):
    """일별 매출 — 지역(KST) 날짜 경계로 묶이고 paid 만 센다(업무일 경계)."""
    day = date(2026, 3, 10)
    kst_midnight_utc = datetime(day.year, day.month, day.day, tzinfo=UTC) - timedelta(hours=9)
    orders = [
        (kst_midnight_utc - timedelta(seconds=1), "100.00", "paid"),  # 전날 23:59:59 KST
        (kst_midnight_utc, "10.00", "paid"),  # 당일 0시 KST
        (kst_midnight_utc + timedelta(hours=23, minutes=59), "5.50", "paid"),
        (kst_midnight_utc + timedelta(hours=1), "999.00", "cancelled"),
    ]
    for at, amount, status in orders:
        world.stack.sql(
            "INSERT INTO sales_orders (id, order_no, customer, total_amount, status, ordered_at, created_at, updated_at) "
            "VALUES (UUID(), %s, 'e2e', %s, %s, %s, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))",
            (unique("ORD")[:32], amount, status, at.replace(tzinfo=None)),
        )
    world.stack.wait_replicated("sales_orders", "customer=%s AND total_amount=%s", ("e2e", "5.50"))
    response = world.client.get(
        "/api/v1/reports/daily-sales",
        params={"start_date": "2026-03-09", "end_date": "2026-03-10"},
        headers=world.as_(world.s),
    )
    assert response.status_code == 200, response.text
    items = {item["sales_date"]: item for item in response.json()["items"]}
    assert float(items["2026-03-09"]["gross_amount"]) == 100.0
    assert float(items["2026-03-10"]["gross_amount"]) == 15.5
    assert items["2026-03-10"]["order_count"] == 2
    covers("scenario", "L3-6 매출")
