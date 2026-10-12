import importlib


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")


def test_worker_include_is_built_from_installed_apps():
    """include 는 ``INSTALLED_APPS`` 의 앱별 ``tasks`` module 이다(service-hardening ADR-012).

    중앙 태스크 module(``app.celery.tasks``)은 없다 — 중앙 파일이 기능을 import 하면
    ``INSTALLED_APPS`` 에서 앱을 빼도 워커가 그 앱을 계속 끌어온다(F-018).
    """
    from app.celery.app import celery_app, discover_task_modules
    from config import INSTALLED_APPS

    assert list(celery_app.conf.include) == discover_task_modules(INSTALLED_APPS)
    assert "app.features.home.tasks" in celery_app.conf.include
    assert "app.celery.tasks" not in celery_app.conf.include


def test_worker_include_drops_an_uninstalled_app():
    """home 을 빼면 include 에서도 빠지고, 남은 include 는 그대로 import 된다."""
    from app.celery.app import discover_task_modules
    from config import INSTALLED_APPS

    subset = [entry for entry in INSTALLED_APPS if not entry.startswith("app.features.home")]
    include = discover_task_modules(subset)

    assert "app.features.home.tasks" not in include
    for module in include:
        importlib.import_module(module)


def test_including_the_task_modules_registers_the_tasks():
    """워커가 include 를 import 하면 태스크가 이름 그대로 등록된다."""
    from app.celery.app import celery_app

    for module in celery_app.conf.include:
        importlib.import_module(module)

    assert "home.aggregate_access_stats" in celery_app.tasks


def test_celery_keeps_internal_times_in_utc():
    """내부 시각은 UTC — DB 저장 기준과 같다(service-hardening ADR-010). ``timezone`` 은 일정 해석용."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE
