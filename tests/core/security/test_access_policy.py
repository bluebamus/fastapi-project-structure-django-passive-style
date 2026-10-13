"""접근 수준 선언 판정과 기본 거부 (access-policy ADR-001~ADR-003).

가드가 보는 것은 라우트의 의존성 트리다. 여기서는 작은 앱을 직접 만들어 규칙마다 하나씩
확인하고, 마지막으로 ``create_app()`` 이 실제로 가드를 부르는지 본다.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI
from starlette.applications import Starlette

from app.core import bootstrap
from app.core.apps import Apps
from app.core.apps.exceptions import ImproperlyConfigured
from app.core.security.access import (
    AccessLevel,
    AccessPolicyGuard,
    LoginRequired,
    Public,
    PublicWrite,
    SuperuserRequired,
)
from app.core.security.dependencies import CurrentPrincipal, SuperuserPrincipal

guard = AccessPolicyGuard()


async def _ok() -> dict:
    return {}


def _violations(app: FastAPI) -> list[str]:
    return guard.violations(app)


def test_undeclared_route_is_a_violation():
    app = FastAPI()
    app.get("/open")(_ok)

    assert _violations(app) == ["GET /open: 접근 수준 선언이 없다"]


def test_two_levels_on_one_route_is_a_violation():
    app = FastAPI()
    app.get("/mixed", dependencies=[Public, LoginRequired])(_ok)

    [found] = _violations(app)
    assert "둘 이상" in found and "login" in found and "public" in found


def test_public_on_a_write_method_points_to_public_write():
    app = FastAPI()
    app.post("/signup", dependencies=[Public])(_ok)

    [found] = _violations(app)
    assert found.startswith("POST /signup") and "PublicWrite" in found


def test_public_write_on_a_safe_method_is_misuse():
    app = FastAPI()
    app.get("/list", dependencies=[PublicWrite])(_ok)

    [found] = _violations(app)
    assert found.startswith("GET /list") and "Public" in found


def test_each_level_is_accepted_where_it_fits():
    app = FastAPI()
    app.get("/a", dependencies=[Public])(_ok)
    app.post("/b", dependencies=[PublicWrite])(_ok)
    app.delete("/c", dependencies=[LoginRequired])(_ok)
    app.put("/d", dependencies=[SuperuserRequired])(_ok)
    # 슈퍼유저는 내부에 로그인을 품는다 — 둘을 함께 적어도 슈퍼유저 하나로 본다.
    app.patch("/e", dependencies=[LoginRequired, SuperuserRequired])(_ok)

    assert _violations(app) == []
    assert guard.levels(app) == {
        ("GET", "/a"): {AccessLevel.PUBLIC},
        ("POST", "/b"): {AccessLevel.PUBLIC_WRITE},
        ("DELETE", "/c"): {AccessLevel.LOGIN},
        ("PUT", "/d"): {AccessLevel.SUPERUSER},
        ("PATCH", "/e"): {AccessLevel.SUPERUSER},
    }


def test_principal_arguments_count_as_declarations():
    app = FastAPI()

    @app.post("/mine")
    async def mine(principal: CurrentPrincipal) -> dict:
        return {}

    @app.get("/admin-report")
    async def report(principal: SuperuserPrincipal) -> dict:
        return {}

    assert _violations(app) == []
    assert guard.levels(app) == {
        ("POST", "/mine"): {AccessLevel.LOGIN},
        ("GET", "/admin-report"): {AccessLevel.SUPERUSER},
    }


def test_router_level_dependencies_count():
    router = APIRouter(dependencies=[SuperuserRequired])
    router.get("/stats")(_ok)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    assert _violations(app) == []
    assert guard.levels(app) == {("GET", "/api/stats"): {AccessLevel.SUPERUSER}}


def test_routes_hidden_from_the_schema_are_still_checked():
    app = FastAPI()
    app.get("/hidden", include_in_schema=False)(_ok)

    assert _violations(app) == ["GET /hidden: 접근 수준 선언이 없다"]


def test_framework_doc_routes_and_mounts_are_excluded():
    """FastAPI 기본 /docs·/redoc·/openapi.json(Starlette Route)과 Mount 는 대상이 아니다."""
    app = FastAPI()
    app.mount("/admin", Starlette())

    assert {getattr(r, "path", "") for r in app.routes} >= {"/docs", "/openapi.json", "/admin"}
    assert guard.levels(app) == {}
    assert _violations(app) == []


def test_nested_includes_are_expanded():
    inner = APIRouter()
    inner.get("/deep")(_ok)
    inner.get("/deep-ok", dependencies=[Public])(_ok)
    outer = APIRouter()
    outer.include_router(inner, prefix="/v1/x")
    app = FastAPI()
    app.include_router(outer, prefix="/api")

    assert _violations(app) == ["GET /api/v1/x/deep: 접근 수준 선언이 없다"]


def test_verify_reports_every_violation_at_once():
    app = FastAPI()
    app.get("/one")(_ok)
    app.post("/two", dependencies=[Public])(_ok)
    app.get("/three", dependencies=[PublicWrite])(_ok)

    with pytest.raises(ImproperlyConfigured) as excinfo:
        guard.verify(app)

    message = str(excinfo.value)
    assert "GET /one" in message and "POST /two" in message and "GET /three" in message


# ---------------------------------------------------------------------------
# 앱 단위
# ---------------------------------------------------------------------------
def test_the_real_app_passes_the_guard():
    app = bootstrap.create_app(registry=Apps(), admin_disabled=True)

    assert guard.violations(app) == []
    assert guard.levels(app)  # 빈 앱이 통과한 것이 아니다


def test_create_app_refuses_to_start_with_an_undeclared_route(monkeypatch):
    """조립 경로에서 가드가 실제로 불린다 — 선언 없는 라우트 하나로 create_app 이 실패한다."""
    real_install = bootstrap.install_routers

    def install_with_a_stray_route(app: FastAPI, registry: Apps) -> list[str]:
        installed = real_install(app, registry)
        app.get("/stray")(_ok)
        return installed

    monkeypatch.setattr(bootstrap, "install_routers", install_with_a_stray_route)

    with pytest.raises(ImproperlyConfigured, match="GET /stray"):
        bootstrap.create_app(registry=Apps(), admin_disabled=True)
