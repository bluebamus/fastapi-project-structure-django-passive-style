"""Celery 태스크 module 발견 (service-hardening ADR-012·C-14).

워커의 ``include`` 는 ``INSTALLED_APPS`` 로 채운 registry 가 만든다. 여기서 고정하는 것:

* 앱에 ``tasks`` module 이 있으면 그 경로, 없으면 빠진다.
* 발견은 module 을 **import 하지 않는다** — 태스크 module 은 ``celery_app`` 을 import 하고,
  ``celery_app`` 은 include 를 만들려고 발견을 부르므로 import 하면 순환이다.
* ``tasks_module`` 은 앱별로 바꿀 수 있다(router·models·admin 과 같은 컨벤션).
"""

import pytest

from app.core.apps import AppConfig, AppRegistryNotReady, Apps

PKG = "tests.core.apps._fixtures"


def test_tasks_module_defaults_to_tasks():
    assert AppConfig.tasks_module == "tasks"


def test_app_with_tasks_module_reports_its_dotted_path(events: list[str]):
    config = AppConfig.create(f"{PKG}.alpha")

    assert config.tasks_module_path() == f"{PKG}.alpha.tasks"
    assert "tasks:alpha" not in events, "발견 단계가 태스크 module 을 import 했다(순환 import 위험)"


def test_app_without_tasks_module_reports_none():
    assert AppConfig.create(f"{PKG}.beta").tasks_module_path() is None


def test_tasks_module_name_is_configurable():
    class RenamedTasks(AppConfig):
        tasks_module = "jobs"

    config = RenamedTasks(f"{PKG}.alpha", AppConfig.create(f"{PKG}.alpha").module)

    assert config.tasks_module_path() is None


def test_registry_lists_task_modules_in_installed_order(registry: Apps, events: list[str]):
    registry.populate([f"{PKG}.beta", f"{PKG}.alpha"], run_ready=False)

    assert registry.task_modules() == [f"{PKG}.alpha.tasks"]
    assert "tasks:alpha" not in events


def test_removing_the_app_removes_its_task_module(registry: Apps):
    registry.populate([f"{PKG}.beta"], run_ready=False)

    assert registry.task_modules() == []


def test_task_modules_requires_population(registry: Apps):
    with pytest.raises(AppRegistryNotReady):
        registry.task_modules()


def test_project_task_modules_follow_installed_apps():
    """실제 ``INSTALLED_APPS`` — home 을 빼면 home 의 태스크도 빠진다."""
    from config import INSTALLED_APPS

    full = Apps()
    full.populate(INSTALLED_APPS, run_ready=False)
    without_home = Apps()
    without_home.populate(
        [entry for entry in INSTALLED_APPS if not entry.startswith("app.features.home")],
        run_ready=False,
    )

    assert "app.features.home.tasks" in full.task_modules()
    assert "app.features.home.tasks" not in without_home.task_modules()
