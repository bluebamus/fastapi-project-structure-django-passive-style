"""AC-08 — 설치 앱의 Admin view 만, 선언 순서대로, 한 번씩 등록된다 (FR-04·NFR-01).

과거 이 프로젝트에는 중앙 취합 파일(``app/features/admin.py``)이 있었고, 새 기능의
관리 화면을 만들고 거기 한 줄 추가하는 것을 잊으면 조용히 빠졌다. 취합을 registry 로
옮겨 그 사각지대를 없앴으므로, 이제 검증해야 할 것은 "취합 목록" 이 아니라
**설치 앱 목록과 등록 결과가 일치하는가** 다.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from sqladmin import Admin, ModelView

from app.core.apps import Apps
from app.core.apps.wiring import install_admin
from app.core.db.session import engine as _ENGINE
from config import INSTALLED_APPS

EXPECTED_MANAGED_MODELS = {"Post", "Reply", "SnsPost", "User", "UserAccessLog"}


@pytest.fixture
def registry() -> Apps:
    apps = Apps()
    apps.populate(INSTALLED_APPS, run_ready=False)
    return apps


def _labels_with_models(registry: Apps) -> list[str]:
    return [config.label for config in registry.get_app_configs() if config.get_models()]


def test_feature_list_is_not_vacuous(registry: Apps):
    """탐지 대상이 비어 있으면 아래 검사들이 헛통과한다."""
    assert len(_labels_with_models(registry)) >= 5


def test_every_app_with_models_owns_an_admin_module(registry: Apps):
    """모델을 가진 설치 앱은 자기 ``admin.py`` 에서 ``admin_views`` 를 노출한다."""
    missing = []
    for label in _labels_with_models(registry):
        config = registry.get_app_config(label)
        module = importlib.import_module(f"{config.name}.{config.admin_module}")
        if not getattr(module, "admin_views", None):
            missing.append(config.name)
    assert not missing, f"admin_views 를 노출하지 않는 앱: {missing}"


def test_installed_apps_admin_views_cover_expected_models(registry: Apps):
    """설치 앱이 관리하는 모델 집합을 고정한다."""
    admin = Admin(FastAPI(), _ENGINE)
    install_admin(admin, registry)

    managed = {view.model.__name__ for view in admin._views}
    assert managed == EXPECTED_MANAGED_MODELS


def test_views_are_registered_in_installed_apps_order(registry: Apps):
    """NFR-01: 등록 순서가 ``INSTALLED_APPS`` 순서를 그대로 따른다."""
    admin = Admin(FastAPI(), _ENGINE)
    install_admin(admin, registry)

    expected: list[type[ModelView]] = []
    for config in registry.get_app_configs():
        expected.extend(config.import_admin_views() or [])

    assert [type(view) for view in admin._views] == expected


def test_each_view_is_registered_exactly_once(registry: Apps):
    """중복 등록은 관리 화면에 같은 메뉴가 두 번 뜨는 것으로 드러난다."""
    admin = Admin(FastAPI(), _ENGINE)
    install_admin(admin, registry)

    names = [type(view).__name__ for view in admin._views]
    assert len(names) == len(set(names)), f"중복 등록된 뷰: {names}"


def test_unregistered_app_views_are_not_installed(registry: Apps):
    """FR-01: 앱을 목록에서 빼면 그 관리 화면도 사라진다."""
    subset = [entry for entry in INSTALLED_APPS if "blog" not in entry]
    partial = Apps()
    partial.populate(subset, run_ready=False)

    admin = Admin(FastAPI(), _ENGINE)
    install_admin(admin, partial)

    assert "Post" not in {view.model.__name__ for view in admin._views}


def test_admin_page_is_mounted_when_enabled():
    """``Admin(...)`` 생성이 ``/admin`` 을 직접 마운트한다 — include_router 는 없다."""
    from app.core.bootstrap import create_app

    app = create_app(registry=Apps(), enable_admin=True)

    assert any(getattr(route, "path", "") == "/admin" for route in app.routes)
