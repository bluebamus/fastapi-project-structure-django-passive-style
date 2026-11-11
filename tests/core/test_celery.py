"""Celery — 앱 구성·태스크 include, async 브리지(run_async), 워커 자원 정리."""

import asyncio
import importlib

import pytest

from app.celery.task import run_async


def test_celery_app_configured():
    from app.celery.app import celery_app

    assert celery_app.conf.broker_url.startswith("redis://")


def test_worker_include_is_built_from_installed_apps():
    """include 는 ``INSTALLED_APPS`` 의 앱별 ``tasks`` module 이다.

    중앙 태스크 module(``app.celery.tasks``)은 없다 — 중앙 파일이 기능을 import 하면
    ``INSTALLED_APPS`` 에서 앱을 빼도 워커가 그 앱을 계속 끌어온다.
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
    """내부 시각은 UTC — DB 저장 기준과 같다. ``timezone`` 은 일정 해석용."""
    from app.celery.app import celery_app
    from config import timezone_settings

    assert celery_app.conf.enable_utc is True
    assert celery_app.conf.timezone == timezone_settings.TIME_ZONE


def test_run_async_reuses_a_single_live_loop() -> None:
    """연속 호출이 '동일한, 닫히지 않은' 루프에서 실행되어야 한다.

    루프 바인딩 자원(aiomysql 커넥션 등)이 태스크 간 재사용돼도 살아남으려면
    이 성질이 필수다. 매 호출 asyncio.run() 이면 루프가 매번 새로 생성·종료되어
    이 단언이 깨진다.
    """
    seen: dict[str, asyncio.AbstractEventLoop] = {}

    async def capture(key: str) -> None:
        seen[key] = asyncio.get_running_loop()

    run_async(capture("first"))
    run_async(capture("second"))

    assert seen["first"] is seen["second"], "연속 태스크가 서로 다른 루프에서 실행됨"
    assert not seen["first"].is_closed(), "재사용 루프가 호출 사이에 닫힘"


def test_run_async_returns_coroutine_result() -> None:
    """브릿지가 코루틴의 반환값을 그대로 전달한다(기존 계약 유지)."""

    async def compute() -> int:
        await asyncio.sleep(0)
        return 21 * 2

    assert run_async(compute()) == 42


# =============================================================================
# Celery worker 자원 종료
# =============================================================================
def test_worker_shutdown_is_a_noop_without_a_loop():
    """태스크를 한 번도 실행하지 않은 worker 는 닫을 것이 없다."""
    from app.celery.lifecycle import shutdown_worker_resources
    from app.celery.task import clear_worker_loop, get_worker_loop

    clear_worker_loop()
    shutdown_worker_resources()

    assert get_worker_loop() is None


def test_worker_shutdown_closes_the_loop(monkeypatch: pytest.MonkeyPatch):
    """worker 가 만든 루프와 그 루프에 묶인 pool 을 닫는다.

    닫지 않으면 커넥션이 서버 쪽에 남고 "Event loop is closed" 경고가 쏟아진다.
    """
    from app.celery import lifecycle, task

    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task, "_worker_loop", loop)

    disposed: list[str] = []

    async def fake_dispose() -> None:
        disposed.append("dispose")

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    lifecycle.shutdown_worker_resources()

    assert disposed == ["dispose"], "루프가 살아 있는 동안 dispose 하지 않았다"
    assert loop.is_closed(), "event loop 를 닫지 않으면 프로세스가 종료되지 않는다"
    assert task.get_worker_loop() is None


def test_worker_shutdown_closes_the_loop_even_if_dispose_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """dispose 가 실패해도 루프는 닫는다 — 안 닫으면 프로세스가 안 죽는다."""
    from app.celery import lifecycle, task

    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task, "_worker_loop", loop)

    async def boom() -> None:
        raise RuntimeError("dispose 실패(모의)")

    monkeypatch.setattr(lifecycle, "dispose_engine", boom)

    lifecycle.shutdown_worker_resources()

    assert loop.is_closed()
    assert task.get_worker_loop() is None
