"""/admin 로그인 통합 흐름 · 로그인 화면 · 세션 사용 범위 (admin-login ADR-001~ADR-003·ADR-006).

조립은 운영과 같다 — ``create_app()`` 이 registry 로 SQLAdmin 을 만들고, ``AuthConfig.ready()``
가 등록한 자격 확인(``UserAdminCredentials``)을 ``AdminAuthBackend`` 에 넣는다. 바꾸는 것은
인프라뿐이다: 자격 확인의 세션 팩토리를 SQLite 파일 DB 로, ``app.state.redis`` 를 fakeredis 로.

계정은 ``scripts/create_superuser.main(... --password-stdin)`` 으로 만든다. 스크립트가
``asyncio.run`` 으로 자기 루프를 돌리므로 스레드에서 부른다.
"""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest_asyncio
import sqlalchemy as sa
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from starlette.middleware.sessions import SessionMiddleware

from app.core.apps import Apps
from app.core.bootstrap import create_app
from app.core.db.session import Base
from app.features.user.models.models import User
from scripts import create_superuser
from tests.admin_login import admin_login

PASSWORD = "Flow-admin-pw-123"
BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
BOOTSTRAP_SRI = "sha384-sRIl4kxILFvY47J16cr9ZwB07vP4J8+LH7qKQnuqkuIAvNWLzeN8tE5YBujZqJLB"


@pytest_asyncio.fixture
async def env(tmp_path) -> AsyncIterator[tuple[AsyncClient, object]]:
    """(client, 세션 팩토리) — SQLite 파일 DB 에 users 테이블만 만든다."""
    path = (tmp_path / "admin.db").as_posix()
    sync_engine = sa.create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync_engine, tables=[User.__table__])
    sync_engine.dispose()

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    app = create_app(registry=Apps(), admin_disabled=False)
    app.state.admin.authentication_backend.credentials.session_factory = factory
    redis = FakeRedis()
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, factory
    await redis.aclose()


async def _create_superuser(factory, username: str) -> int:
    return await asyncio.to_thread(
        create_superuser.main,
        ["--username", username, "--email", f"{username}@x.com", "--password-stdin"],
        session_factory=factory,
        stdin=io.StringIO(f"{PASSWORD}\n"),
    )


async def _login(client: AsyncClient, username: str, password: str = PASSWORD):
    return await admin_login(client, username, password)


# ---------------------------------------------------------------------------
# 통합 흐름
# ---------------------------------------------------------------------------
async def test_superuser_from_the_script_can_log_in_and_out(env):
    client, factory = env
    assert await _create_superuser(factory, "ops-root") == 0

    before = await client.get("/admin/")
    assert before.status_code == 302
    assert before.headers["location"].endswith("/admin/login")

    assert (await _login(client, "ops-root", "wrong-password")).status_code == 400

    logged_in = await _login(client, "ops-root")
    assert logged_in.status_code == 302
    assert logged_in.headers["location"].endswith("/admin/")
    assert (await client.get("/admin/")).status_code == 200

    assert (await client.get("/admin/logout")).status_code == 302
    assert (await client.get("/admin/")).status_code == 302


async def test_regular_user_cannot_log_in(env):
    client, factory = env
    assert await _create_superuser(factory, "demoted") == 0
    async with factory() as session:
        await session.execute(
            sa.update(User).where(User.username == "demoted").values(is_superuser=False)
        )
        await session.commit()

    assert (await _login(client, "demoted")).status_code == 400
    assert (await client.get("/admin/")).status_code == 302


async def test_demotion_in_the_database_ends_the_admin_session(env):
    client, factory = env
    await _create_superuser(factory, "boss")
    await _login(client, "boss")
    assert (await client.get("/admin/")).status_code == 200

    async with factory() as session:
        await session.execute(
            sa.update(User).where(User.username == "boss").values(is_active=False)
        )
        await session.commit()

    assert (await client.get("/admin/")).status_code == 302


# ---------------------------------------------------------------------------
# 로그인 화면 (Bootstrap)
# ---------------------------------------------------------------------------
async def test_login_page_is_the_bootstrap_screen(env):
    client, _ = env

    response = await client.get("/admin/login")

    assert response.status_code == 200
    html = response.text
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="ko">' in html
    assert 'name="viewport"' in html
    assert f'href="{BOOTSTRAP_CSS}"' in html
    assert f'integrity="{BOOTSTRAP_SRI}"' in html
    assert 'crossorigin="anonymous"' in html
    assert "<script" not in html, "로그인 화면에 JS 가 필요 없다"
    assert 'action="http://test/admin/login"' in html and 'method="POST"' in html
    for field, autocomplete in (("username", "username"), ("password", "current-password")):
        tag = re.search(rf"<input[^>]*name=\"{field}\"[^>]*>", html, re.DOTALL)
        assert tag, f"{field} 입력이 없다"
        assert f'autocomplete="{autocomplete}"' in tag.group(0)
        assert "required" in tag.group(0)
        assert f'id="{field}"' in tag.group(0)
        assert f'<label for="{field}"' in html, f"{field} 레이블이 입력에 연결되지 않았다"
    assert "autofocus" in re.search(r"<input[^>]*name=\"username\"[^>]*>", html, re.DOTALL).group(0)
    assert "Admin</h1>" in html, "제목(admin.title)이 없다"
    # CSRF 토큰은 폼 안의 hidden 입력이다(security-ops-hardening ADR-004).
    form = re.search(r"<form.*?</form>", html, re.DOTALL).group(0)
    assert re.search(r'<input type="hidden" name="csrf_token" value="[A-Za-z0-9_-]{43,}">', form)


async def test_login_page_escapes_the_error_message(env):
    client, _ = env
    templates = client._transport.app.state.admin.templates  # type: ignore[attr-defined]

    class _Request(dict):
        session: dict = {}

        def url_for(self, name: str, **_: object) -> str:
            return "/admin/login"

    html = await templates.env.get_template("sqladmin/login.html").render_async(
        request=_Request(), error="<script>alert(1)</script>"
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert 'class="alert alert-danger"' in html


# ---------------------------------------------------------------------------
# 세션 사용 범위 — 세션은 /admin 전용이다 (admin-login ADR-006)
# ---------------------------------------------------------------------------
async def test_session_middleware_lives_only_in_the_admin_sub_app(env):
    client, _ = env
    app = client._transport.app  # type: ignore[attr-defined]

    main_stack = [m.cls for m in app.user_middleware]
    admin_stack = [m.cls for m in app.state.admin.admin.user_middleware]

    assert SessionMiddleware not in main_stack, "메인 앱에 세션 미들웨어가 붙었다"
    assert admin_stack.count(SessionMiddleware) == 1


async def test_admin_session_cookie_does_not_authenticate_the_api(env):
    client, factory = env
    await _create_superuser(factory, "apiroot")
    await _login(client, "apiroot")
    cookie = client.cookies.get("admin_session")
    assert cookie

    # path=/admin 쿠키라 jar 는 /api 로 보내지 않는다 — 직접 실어 보내도 API 는 받지 않는다.
    me = await client.get("/api/v1/auth/me", headers={"Cookie": f"admin_session={cookie}"})
    users = await client.get("/api/v1/user/users", headers={"Cookie": f"admin_session={cookie}"})

    assert me.status_code == 401
    assert users.status_code == 401


async def test_admin_session_cookie_is_never_set_outside_admin(env):
    client, factory = env
    await _create_superuser(factory, "scoped")
    await _login(client, "scoped")

    for path in ("/health", "/ready", "/api/v1/auth/me", "/api/v1/user/users", "/openapi.json"):
        response = await client.get(path)
        assert "admin_session" not in response.headers.get("set-cookie", ""), path
