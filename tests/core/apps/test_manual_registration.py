"""AC-06 — 미등록 앱은 **어떤 결선에도 참여하지 않는다** (FR-01·FR-04·SEC-02).

이 프로젝트의 존재 이유가 여기 걸려 있다. "디렉터리를 만들면 앱이 생긴다" 는
자동 스캔 방식과 달리, passive 등록에서는 ``config.INSTALLED_APPS`` 에 없는 앱은
route 에도, ``Base.metadata`` 에도, Admin view 에도, ``ready()`` 이벤트에도 나오지
않아야 한다. 네 곳 전부를 한 파일에서 대조한다 — 하나만 새도 계약은 깨진 것이다.
"""

from __future__ import annotations

import sys

from fastapi import FastAPI

from app.core.apps import Apps
from app.core.apps.wiring import install_routers
from config import INSTALLED_APPS

PKG = "tests.core.apps._fixtures"


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def _build(entries: list[str]) -> FastAPI:
    """격리 registry 로 route 만 설치한 최소 앱을 만든다."""
    registry = Apps()
    registry.populate(entries)
    app = FastAPI()
    install_routers(app, registry)
    return app


def test_removing_an_app_removes_its_routes():
    """auth 를 목록에서 빼면 auth route 가 사라진다."""
    full = _paths(_build(list(INSTALLED_APPS)))
    without_auth = _paths(_build([e for e in INSTALLED_APPS if "auth" not in e]))

    assert any(p.startswith("/api/v1/auth") for p in full), "대조군이 비어 있다"
    assert not any(p.startswith("/api/v1/auth") for p in without_auth)
    assert without_auth < full


def test_routes_follow_installed_apps_order():
    """NFR-01: router 설치 순서가 목록 순서를 따른다."""
    registry = Apps()
    registry.populate(list(INSTALLED_APPS))

    installed = install_routers(FastAPI(), registry)

    assert installed == [config.label for config in registry.get_app_configs()]


def test_unregistered_fixture_app_is_never_imported(events: list[str]):
    """SEC-02: allowlist 밖의 package 는 import 되지 않는다."""
    registry = Apps()
    registry.populate([f"{PKG}.alpha"])

    assert f"{PKG}.unregistered" not in sys.modules
    assert not [e for e in events if e.endswith(":unregistered")]


def test_unregistered_app_contributes_no_models():
    """미등록 앱의 model 은 registry 수집에 없다."""
    registry = Apps()
    registry.populate([f"{PKG}.alpha"])

    assert {m.__name__ for m in registry.get_models()} == {"AlphaThing"}
    assert registry.is_installed(f"{PKG}.beta") is False


def test_directory_presence_alone_does_not_install(events: list[str]):
    """FR-01: fixture 디렉터리가 존재해도 목록에 없으면 설치되지 않는다."""
    from pathlib import Path

    fixtures_dir = Path(__file__).parent / "_fixtures"
    assert (fixtures_dir / "unregistered" / "apps.py").is_file(), "대조군 fixture 가 없다"

    registry = Apps()
    registry.populate([f"{PKG}.plain"])

    assert [c.label for c in registry.get_app_configs()] == ["plain"]
    assert events == []
