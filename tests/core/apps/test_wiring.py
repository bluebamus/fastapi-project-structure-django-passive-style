"""FastAPI adapter 의 실패 계약 (FR-04·CR-08·SEC-07).

adapter 가 조용히 넘어가면 안 되는 두 상황을 고정한다.

* **route 충돌** — 두 앱이 같은 method+path 를 등록하면 나중 것이 그림자에 가려
  요청이 엉뚱한 앱으로 간다. 증상은 "가끔 404" 나 "권한이 다른 응답" 으로 나타나
  원인을 찾기 어렵다. 기동 시점에 실패시킨다.
* **module 은 있는데 공개 이름이 없음** — 오타 하나가 "이 앱은 라우터가 없나 보다"
  로 흡수되면 안 된다. 부재(module 자체 없음)와 구별해 실패시킨다.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI

from app.core.apps import AppConfig, Apps
from app.core.apps.exceptions import ImproperlyConfigured
from app.core.apps.wiring import install_admin, install_routers

PKG = "tests.core.apps._fixtures"


SHARED_PATH = "/v1/shared/resource"


def _config_serving(label: str) -> AppConfig:
    """``SHARED_PATH`` 를 등록하는 합성 ``AppConfig``.

    실제 앱의 path 를 빌려 오면 그 앱이 route 를 바꾸는 순간 이 테스트가 무관하게
    깨진다. 충돌 자체만 재현한다.
    """
    import importlib

    module = importlib.import_module(f"{PKG}.alpha")

    class _Colliding(AppConfig):
        name = f"{PKG}.alpha"

        def import_router(self):
            router = APIRouter()

            @router.get(SHARED_PATH)
            async def handler() -> dict[str, str]:
                return {}

            return router

    _Colliding.label = label
    return _Colliding(f"{PKG}.alpha", module)


def test_app_without_router_is_skipped(registry: Apps):
    """router module 이 없는 앱은 건너뛴다 — 오류가 아니다."""
    registry.populate([f"{PKG}.plain"])

    installed = install_routers(FastAPI(), registry)

    assert installed == []


def test_route_collision_fails_fast(registry: Apps):
    """FR-04: 같은 method+path 를 두 앱이 등록하면 기동을 실패시킨다."""
    registry.populate([f"{PKG}.plain"])
    registry.app_configs["first"] = _config_serving("first")
    registry.app_configs["second"] = _config_serving("second")

    with pytest.raises(ImproperlyConfigured) as exc:
        install_routers(FastAPI(), registry)

    message = str(exc.value)
    assert "first" in message and "second" in message
    assert f"/api{SHARED_PATH}" in message
    assert "GET" in message


def test_missing_public_name_in_existing_module_fails(registry: Apps):
    """SEC-07: module 은 있는데 기대한 이름이 없으면 실패한다."""
    registry.populate([f"{PKG}.alpha"])
    config = registry.get_app_config("alpha")
    config.router_module = "apps"  # 존재하는 module, 하지만 alpha_router 는 없다

    with pytest.raises(ImproperlyConfigured) as exc:
        install_routers(FastAPI(), registry)

    assert "alpha_router" in str(exc.value)


def test_install_admin_skips_apps_without_admin_module(registry: Apps):
    """admin module 이 없는 앱은 조용히 건너뛴다."""

    class _Admin:
        def __init__(self) -> None:
            self.views: list[type] = []

        def add_view(self, view: type) -> None:
            self.views.append(view)

    registry.populate([f"{PKG}.alpha", f"{PKG}.plain"])
    admin = _Admin()

    registered = install_admin(admin, registry)  # type: ignore[arg-type]

    assert registered == []
    assert admin.views == []
