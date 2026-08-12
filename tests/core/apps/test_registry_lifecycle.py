"""AC-04 — populate() 의 idempotency·재진입 금지·thread safety (NFR-02·NFR-05·CR-07).

전역 registry 를 여러 진입점(app factory, Alembic, 테스트)이 공유하므로 "두 번
불러도 안전한가" 가 곧 정확성이다. ``ready()`` 가 두 번 돌면 sink 나 signal 이 중복
등록된다.
"""

import threading

import pytest

from app.core.apps import Apps

PKG = "tests.core.apps._fixtures"
TWO_APPS = [f"{PKG}.alpha", f"{PKG}.beta"]


def test_second_populate_is_a_noop(registry: Apps, events: list[str]):
    """CR-07: 두 번째 정상 호출은 ``ready()`` 를 다시 부르지 않는다."""
    registry.populate(TWO_APPS)
    before = list(events)

    registry.populate(TWO_APPS)

    assert events == before
    assert events.count("ready:alpha") == 1


def test_reentrant_populate_during_ready_is_rejected(events: list[str]):
    """NFR-02: population 중 재진입은 즉시 명시적 오류다."""
    registry = Apps()
    captured: list[BaseException] = []

    class ReentrantConfig(Apps):
        pass

    def hook() -> None:
        try:
            registry.populate(TWO_APPS)
        except BaseException as exc:  # noqa: BLE001 - 재진입 오류 종류를 확인한다
            captured.append(exc)

    original = Apps._run_ready

    def patched(self: Apps) -> None:
        hook()
        original(self)

    Apps._run_ready = patched  # type: ignore[method-assign]
    try:
        registry.populate(TWO_APPS)
    finally:
        Apps._run_ready = original  # type: ignore[method-assign]

    assert captured, "재진입 호출이 오류를 내지 않았다"
    assert isinstance(captured[0], RuntimeError)
    assert events.count("ready:alpha") == 1


def test_concurrent_populate_completes_once(events: list[str]):
    """NFR-02: 동시 호출에서도 ``ready()`` 는 앱별로 한 번만 실행된다."""
    registry = Apps()
    barrier = threading.Barrier(4)
    errors: list[BaseException] = []

    def worker() -> None:
        barrier.wait()
        try:
            registry.populate(TWO_APPS)
        except BaseException as exc:  # noqa: BLE001 - 실패를 본 스레드를 수집한다
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, errors
    assert registry.ready is True
    assert events.count("ready:alpha") == 1
    assert events.count("ready:beta") == 1


def test_isolated_registries_do_not_share_state(events: list[str]):
    """NFR-05: 독립 인스턴스는 서로의 상태를 오염시키지 않는다."""
    first = Apps()
    second = Apps()

    first.populate([f"{PKG}.alpha"])

    assert second.ready is False
    with pytest.raises(Exception, match="registry"):
        second.get_app_configs()


def test_models_only_population_skips_ready(events: list[str]):
    """§6.7: Alembic adapter 용 ``run_ready=False`` 는 hook 을 실행하지 않는다."""
    registry = Apps()

    registry.populate(TWO_APPS, run_ready=False)

    assert registry.models_ready is True
    assert registry.ready is False
    assert not [e for e in events if e.startswith("ready:")]
    assert {m.__name__ for m in registry.get_models()} == {"AlphaThing", "BetaThing"}
