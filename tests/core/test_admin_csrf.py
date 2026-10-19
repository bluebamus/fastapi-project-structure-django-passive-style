"""로그인 이후 관리 화면 CSRF · POST 로그아웃 · 관리 화면 쪽 세션 폐기 (admin-session-hardening ADR-001~003).

조립은 운영과 같다(``create_app``) — 관리 뷰·세션 팩토리만 in-memory SQLite 로, Redis 는 fakeredis 로.

sqladmin 0.32 가 상태를 바꾸는 요청과 이 저장소의 보호:

==================  ==========================================  =============================
요청                 sqladmin 이 보내는 방식                       토큰
==================  ==========================================  =============================
로그인               로그인 폼 POST(덮어쓴 login.html)             hidden ``csrf_token``
생성                 ``create.html`` 폼 POST(multipart)            스크립트가 hidden 추가
수정                 ``edit.html`` 폼 POST(multipart)              스크립트가 hidden 추가
삭제(행)             모달 → ``$.ajax`` DELETE ``?pks=``            스크립트가 XHR 헤더 추가
일괄 삭제            목록 작업 → 같은 모달 → ``$.ajax`` DELETE       스크립트가 XHR 헤더 추가
가져오기(CSV)        모달 → ``fetch`` POST(FormData)               스크립트가 fetch 헤더 추가
로그아웃             ``layout.html`` 의 GET 링크 → POST 전용으로     스크립트가 POST 폼으로 제출
==================  ==========================================  =============================

목록·상세·내보내기·ajax 조회·파일 내려받기는 GET 조회라 토큰을 보지 않는다.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqladmin
import sqlalchemy as sa
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.apps import Apps
from app.core.bootstrap import create_app
from app.core.db.session import Base
from app.core.security.admin_auth import CSRF_FAILED_MESSAGE, AdminCsrfMiddleware
from app.core.security.admin_session import RedisSessionMiddleware
from app.core.security.dependencies import get_password_hasher
from app.features.catalog.models.models import Product
from app.features.user.models.models import User
from tests.admin_login import admin_login, admin_page_token

PASSWORD = "Csrf-admin-pw-123"
SQLADMIN_DIR = Path(sqladmin.__file__).resolve().parent


def _seed() -> list[object]:
    hashed = get_password_hasher().hash(PASSWORD)
    return [
        User(
            id="u-root", username="root", email="r@x.com", hashed_password=hashed, is_superuser=True
        ),
        User(
            id="u-boss", username="boss", email="b@x.com", hashed_password=hashed, is_superuser=True
        ),
        *(
            Product(id=f"pr-{i}", sku=f"SKU-{i}", name=f"상품{i}", price=Decimal("1.00"), stock=1)
            for i in range(1, 4)
        ),
    ]


@pytest_asyncio.fixture
async def env() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker, FakeRedis]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(_seed())
        await session.commit()

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app = create_app(registry=Apps(), admin_disabled=False)
    admin = app.state.admin
    admin.authentication_backend.credentials.session_factory = factory
    for view in admin._views:
        view.session_maker = maker
        view.is_async = True
    redis = FakeRedis()
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await admin_login(client, "root", PASSWORD)).status_code == 302
        yield client, maker, redis
    await redis.aclose()
    await engine.dispose()


async def _product_ids(maker) -> set[str]:
    async with maker() as session:
        return set((await session.execute(sa.select(Product.id))).scalars())


async def _product_name(maker, pk: str) -> str:
    async with maker() as session:
        return (await session.execute(sa.select(Product.name).where(Product.id == pk))).scalar_one()


def _product_form(**extra: str) -> dict[str, str]:
    return {
        "sku": "SKU-NEW",
        "name": "새 상품",
        "price": "3.50",
        "stock": "2",
        "is_active": "y",
    } | extra


# ---------------------------------------------------------------------------
# 상태를 바꾸는 요청 — 토큰 없음·틀림·다른 세션 토큰은 403, 상태 그대로
# ---------------------------------------------------------------------------
_REQUESTS = {
    "create": ("POST", "/admin/product/create", _product_form()),
    "edit": ("POST", "/admin/product/edit/pr-1", _product_form(sku="SKU-1", name="바뀜")),
    "delete": ("DELETE", "/admin/product/delete?pks=pr-1", None),
    "bulk-delete": ("DELETE", "/admin/product/delete?pks=pr-2,pr-3", None),
    "logout": ("POST", "/admin/logout", {}),
}


async def _send(client: AsyncClient, name: str, token: str | None, *, via: str = "form"):
    method, url, form = _REQUESTS[name]
    headers = {"X-CSRF-Token": token} if via == "header" and token is not None else {}
    data = dict(form) if form is not None else None
    if via == "form" and token is not None and data is not None:
        data["csrf_token"] = token
    if data is None:
        return await client.request(method, url, headers=headers)
    return await client.request(method, url, data=data, headers=headers)


async def _state(client: AsyncClient, maker) -> tuple[set[str], str, int]:
    return (
        await _product_ids(maker),
        await _product_name(maker, "pr-1"),
        (await client.get("/admin/")).status_code,
    )


@pytest.mark.parametrize("name", list(_REQUESTS))
@pytest.mark.parametrize("token_kind", ["missing", "wrong", "other-session"])
async def test_state_changing_request_without_the_session_token_is_403(env, name, token_kind):
    client, maker, _ = env
    before = await _state(client, maker)
    token = {"missing": None, "wrong": "x" * 43}.get(token_kind)
    if token_kind == "other-session":
        app = client._transport.app  # type: ignore[attr-defined]
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
            await admin_login(other, "boss", PASSWORD)
            token = await admin_page_token(other)

    for via in ("form", "header"):
        response = await _send(client, name, token, via=via)
        assert response.status_code == 403, (via, response.status_code)
        assert CSRF_FAILED_MESSAGE in response.text

    assert await _state(client, maker) == before, "403 인데 상태가 바뀌었다(또는 로그아웃됐다)"


async def test_rejection_for_a_logged_in_user_is_the_admin_error_page(env):
    client, _, _ = env

    response = await client.post("/admin/product/create", data=_product_form())

    assert response.status_code == 403
    assert "text/html" in response.headers["content-type"]
    assert 'meta name="csrf-token"' in response.text, "관리 화면 맥락(레이아웃)이 아니다"


async def test_rejection_without_login_does_not_render_the_admin_layout():
    app = create_app(registry=Apps(), admin_disabled=False)
    app.state.redis = FakeRedis()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/admin/product/create", data=_product_form())

    assert response.status_code == 403
    assert response.text == CSRF_FAILED_MESSAGE, "로그인 전인데 관리 메뉴(모델 이름)를 그렸다"


# ---------------------------------------------------------------------------
# 맞는 토큰 — 폼·헤더 두 경로 모두 정상 동작
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("via", ["form", "header"])
async def test_create_with_the_token(env, via):
    client, maker, _ = env

    response = await _send(client, "create", await admin_page_token(client), via=via)

    assert response.status_code == 302
    assert len(await _product_ids(maker)) == 4


@pytest.mark.parametrize("via", ["form", "header"])
async def test_edit_with_the_token(env, via):
    client, maker, _ = env

    response = await _send(client, "edit", await admin_page_token(client), via=via)

    assert response.status_code == 302
    assert await _product_name(maker, "pr-1") == "바뀜"


async def test_delete_and_bulk_delete_with_the_header_token(env):
    client, maker, _ = env
    token = await admin_page_token(client)

    single = await _send(client, "delete", token, via="header")
    bulk = await _send(client, "bulk-delete", token, via="header")

    assert (single.status_code, bulk.status_code) == (200, 200)
    assert await _product_ids(maker) == set()


async def test_import_reaches_sqladmin_only_with_the_token(env):
    """가져오기는 ``fetch`` 로 보낸다(헤더). 이 저장소의 뷰는 가져오기를 열지 않아 sqladmin 이 막는다 —
    토큰이 없으면 sqladmin 까지 가지도 못한다(CSRF 문구)."""
    client, _, _ = env
    files = {"csvfile": ("p.csv", b"sku,name\n", "text/csv")}

    without = await client.post("/admin/product/import", files=files)
    with_token = await client.post(
        "/admin/product/import",
        files=files,
        headers={"X-CSRF-Token": await admin_page_token(client)},
    )

    assert without.status_code == 403 and CSRF_FAILED_MESSAGE in without.text
    assert CSRF_FAILED_MESSAGE not in with_token.text


async def test_logout_with_the_token_and_a_copied_cookie_is_refused_afterwards(env):
    client, _, _ = env
    copied = client.cookies["admin_session"]

    response = await _send(client, "logout", await admin_page_token(client))

    assert response.status_code == 302
    assert (await client.get("/admin/")).status_code == 302
    client.cookies.set("admin_session", copied, domain="test.local", path="/admin")
    assert (await client.get("/admin/")).status_code == 302, "로그아웃한 세션의 쿠키 사본이 통했다"


async def test_logout_by_get_is_refused_and_keeps_the_session(env):
    """``<img src="/admin/logout">`` 로 강제 로그아웃시킬 수 없다."""
    client, _, _ = env

    response = await client.get("/admin/logout")

    assert response.status_code == 405
    assert (await client.get("/admin/")).status_code == 200


async def test_reads_need_no_token(env):
    client, _, _ = env

    for url in (
        "/admin/",
        "/admin/product/list",
        "/admin/product/details/pr-1",
        "/admin/product/create",
        "/admin/product/edit/pr-1",
        "/admin/product/export/csv",
    ):
        assert (await client.get(url)).status_code == 200, url


# ---------------------------------------------------------------------------
# 화면 — meta 토큰과 스크립트
# ---------------------------------------------------------------------------
async def test_admin_pages_carry_the_session_token_and_the_script(env):
    client, _, redis = env

    for url in (
        "/admin/",
        "/admin/product/list",
        "/admin/product/create",
        "/admin/product/edit/pr-1",
    ):
        html = (await client.get(url)).text
        assert html.count('<meta name="csrf-token"') == 1, url
        assert "X-CSRF-Token" in html and "csrf_token" in html, url
    # 스크립트의 세 갈래 — 폼 hidden·XHR/fetch 헤더·로그아웃 POST(실제 동작은 browser 테스트가 본다).
    for snippet in (
        "addToken(form);",
        "this.setRequestHeader('X-CSRF-Token', token);",
        "headers.set('X-CSRF-Token', token);",
        "form.method = 'post';",
    ):
        assert snippet in html, f"스크립트에 {snippet!r} 가 없다"
    token = await admin_page_token(client)
    assert re.fullmatch(r"[A-Za-z0-9_-]{43,}", token)
    assert '"http://test/admin/logout"' in html, "스크립트가 로그아웃 주소를 모른다"
    assert await admin_page_token(client, "/admin/product/list") == token, "화면마다 토큰이 바뀐다"


# ---------------------------------------------------------------------------
# 관리 화면에서의 강등·비활성화·삭제 → 그 사용자의 관리 세션 즉시 폐기
# ---------------------------------------------------------------------------
async def _boss_client(app) -> AsyncClient:
    other = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    assert (await admin_login(other, "boss", PASSWORD)).status_code == 302
    return other


async def _boss_index(redis: FakeRedis) -> set[bytes]:
    return set(await redis.smembers("admin:user_sessions:u-boss"))


@pytest.mark.parametrize(
    "form",
    [
        {"username": "boss", "email": "b@x.com", "is_active": "y"},  # 슈퍼유저 해제
        {"username": "boss", "email": "b@x.com", "is_superuser": "y"},  # 비활성화
    ],
    ids=["demote", "deactivate"],
)
async def test_admin_edit_that_drops_the_privilege_revokes_that_users_sessions(env, form):
    client, _, redis = env
    app = client._transport.app  # type: ignore[attr-defined]
    boss = await _boss_client(app)
    keys_before = await _boss_index(redis)
    assert keys_before

    response = await client.post(
        "/admin/user/edit/u-boss", data={**form, "csrf_token": await admin_page_token(client)}
    )

    assert response.status_code == 302
    assert await _boss_index(redis) == set()
    for key in keys_before:
        assert not await redis.exists(key), "강등·비활성화된 사용자의 세션 키가 남았다"
    stale = await boss.get("/admin/")
    assert stale.status_code == 302
    await boss.aclose()


async def test_self_demotion_ends_the_current_session_too(env):
    """자기 자신을 강등하면 지금 세션도 지워진다 — 의도(ADR-005)."""
    client, _, redis = env

    response = await client.post(
        "/admin/user/edit/u-root",
        data={
            "username": "root",
            "email": "r@x.com",
            "is_active": "y",
            "csrf_token": await admin_page_token(client),
        },
    )

    assert response.status_code == 302
    assert set(await redis.smembers("admin:user_sessions:u-root")) == set()
    assert (await client.get("/admin/")).status_code == 302


async def test_admin_edit_on_an_already_inactive_user_does_not_revoke(env, monkeypatch):
    """변경 전후 비교 — 이미 비활성인 사용자의 이메일만 바꾸면 폐기하지 않는다."""
    client, maker, _ = env
    async with maker() as session:
        await session.execute(sa.update(User).where(User.id == "u-boss").values(is_active=False))
        await session.commit()
    calls: list[str] = []

    async def spy(self, user_id: str) -> None:
        calls.append(user_id)

    monkeypatch.setattr("app.core.security.admin_session.AdminSessionStore.revoke_user", spy)
    response = await client.post(
        "/admin/user/edit/u-boss",
        data={
            "username": "boss",
            "email": "b3@x.com",
            "is_superuser": "y",
            "csrf_token": await admin_page_token(client),
        },
    )

    assert response.status_code == 302
    assert calls == []


async def test_redis_failure_while_revoking_is_not_swallowed(env, monkeypatch):
    """폐기 중 Redis 오류는 삼키지 않는다 — sqladmin 이 오류 화면(400)으로 드러낸다."""
    from redis.exceptions import ConnectionError as RedisConnectionError

    client, _, _ = env

    async def down(self, user_id: str) -> None:
        raise RedisConnectionError("down")

    monkeypatch.setattr("app.core.security.admin_session.AdminSessionStore.revoke_user", down)
    response = await client.post(
        "/admin/user/edit/u-boss",
        data={
            "username": "boss",
            "email": "b@x.com",
            "is_active": "y",
            "csrf_token": await admin_page_token(client),
        },
    )

    assert response.status_code == 400
    assert "down" in response.text


async def test_admin_edit_that_keeps_the_privilege_keeps_the_sessions(env):
    client, _, redis = env
    boss = await _boss_client(client._transport.app)  # type: ignore[attr-defined]

    await client.post(
        "/admin/user/edit/u-boss",
        data={
            "username": "boss",
            "email": "b2@x.com",
            "is_active": "y",
            "is_superuser": "y",
            "csrf_token": await admin_page_token(client),
        },
    )

    assert await _boss_index(redis)
    assert (await boss.get("/admin/")).status_code == 200
    await boss.aclose()


async def test_admin_delete_revokes_that_users_sessions(env):
    client, _, redis = env
    boss = await _boss_client(client._transport.app)  # type: ignore[attr-defined]
    keys_before = await _boss_index(redis)

    response = await client.delete(
        "/admin/user/delete?pks=u-boss", headers={"X-CSRF-Token": await admin_page_token(client)}
    )

    assert response.status_code == 200
    assert await _boss_index(redis) == set()
    for key in keys_before:
        assert not await redis.exists(key)
    await boss.aclose()


# ---------------------------------------------------------------------------
# 조립 — 미들웨어 위치와 순서
# ---------------------------------------------------------------------------
async def test_session_and_csrf_middlewares_live_only_in_the_admin_sub_app(env):
    client, _, _ = env
    app = client._transport.app  # type: ignore[attr-defined]

    main_stack = [m.cls for m in app.user_middleware]
    admin_stack = [m.cls for m in app.state.admin.admin.user_middleware]

    assert not {RedisSessionMiddleware, AdminCsrfMiddleware} & set(main_stack)
    assert "SessionMiddleware" not in [c.__name__ for c in admin_stack], "서명 쿠키 세션이 남았다"
    assert admin_stack.index(RedisSessionMiddleware) < admin_stack.index(
        AdminCsrfMiddleware
    ), "CSRF 가 세션보다 바깥이면 세션 토큰을 읽지 못한다"


# ---------------------------------------------------------------------------
# sqladmin 원본 대조 — 버전을 올려 덮어쓴 base.html·스크립트의 전제가 깨지면 실패한다
# ---------------------------------------------------------------------------
def _upstream(relative: str) -> str:
    return (SQLADMIN_DIR / relative).read_text(encoding="utf-8")


def test_upstream_base_template_still_has_the_blocks_we_extend():
    base = _upstream("templates/sqladmin/base.html")

    assert "{% block head_meta %}" in base and "{% block tail_js %}" in base
    assert "js/main.js" in base, "main.js 가 tail_js 밖으로 옮겨졌다 — 스크립트 순서를 다시 보라"


def test_upstream_logout_is_still_a_get_link_in_the_layout():
    layout = _upstream("templates/sqladmin/layout.html")

    assert '{% extends "sqladmin/base.html" %}' in layout
    assert "<a href=\"{{ request.url_for('admin:logout') }}\"" in layout


def test_upstream_requests_still_go_through_form_xhr_and_fetch():
    main_js = _upstream("statics/js/main.js")
    create = _upstream("templates/sqladmin/create.html")
    edit = _upstream("templates/sqladmin/edit.html")

    assert "$.ajax({" in main_js and "method: 'DELETE'" in main_js, "삭제가 XHR 이 아니다"
    assert "fetch(frm.attr('action')" in main_js, "가져오기가 fetch 가 아니다"
    assert (
        "window.location.href = $(this).attr('data-url')" in main_js
    ), "사용자 정의 작업 방식이 바뀌었다"
    for page in (create, edit):
        assert 'method="POST"' in page and 'enctype="multipart/form-data"' in page
    application = _upstream("application.py")
    assert 'Route("/logout", endpoint=self.logout, name="logout", methods=["GET"])' in application


def test_our_base_template_extends_the_original_and_is_picked_first(env):
    client, _, _ = env
    templates = client._transport.app.state.admin.templates  # type: ignore[attr-defined]

    ours = templates.env.get_template("sqladmin/base.html")
    original = templates.env.get_template("sqladmin_original/base.html")

    assert Path(ours.filename).parent.name == "sqladmin" and "app" in Path(ours.filename).parts
    assert Path(original.filename).resolve() == (SQLADMIN_DIR / "templates/sqladmin/base.html")
