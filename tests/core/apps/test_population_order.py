"""AC-02 — 3단계 population 순서와 준비 상태 (CR-03·CR-05·NFR-01).

Django 는 앱을 목록 순서대로 ``config/root package → models → ready()`` 세 단계로
초기화한다. 단계는 **앱별로 겹치지 않는다** — 모든 앱의 models 가 끝나기 전에 어떤
앱의 ``ready()`` 도 호출되지 않는다. 이 파일이 그 계약을 이벤트 로그로 고정한다.
"""

from app.core.apps import Apps

PKG = "tests.core.apps._fixtures"
TWO_APPS = [f"{PKG}.alpha", f"{PKG}.beta"]


def test_population_runs_three_phases_in_order(registry: Apps, events: list[str]):
    """CR-03: 단계가 앱별로 섞이지 않고 phase 단위로 진행된다."""
    registry.populate(TWO_APPS)

    assert events == [
        "config:alpha",
        "config:beta",
        "models:alpha",
        "models:beta",
        "ready:alpha",
        "ready:beta",
    ]


def test_installed_apps_order_is_preserved(registry: Apps, events: list[str]):
    """NFR-01: 목록 순서를 뒤집으면 모든 단계의 순서가 함께 뒤집힌다."""
    registry.populate(list(reversed(TWO_APPS)))

    assert [e for e in events if e.startswith("ready:")] == ["ready:beta", "ready:alpha"]
    assert [c.label for c in registry.get_app_configs()] == ["beta", "alpha"]


def test_ready_flags_flip_only_after_each_phase_completes(registry: Apps):
    """CR-05: 세 flag 는 해당 단계가 전체 앱에 대해 끝난 뒤에만 True 다."""
    assert (registry.apps_ready, registry.models_ready, registry.ready) == (False, False, False)

    registry.populate(TWO_APPS)

    assert (registry.apps_ready, registry.models_ready, registry.ready) == (True, True, True)


def test_root_package_import_does_not_load_models(registry: Apps, events: list[str]):
    """Phase 3 완료 조건: 1단계에서 models 가 로드되면 안 된다."""
    seen: list[str] = []

    class Probe(Apps):
        def _import_models(self) -> None:
            seen.extend(events)
            super()._import_models()

    Probe().populate(TWO_APPS)

    assert seen == ["config:alpha", "config:beta"]


def test_query_api_reflects_installed_apps(registry: Apps):
    """FR-05: 조회 API 가 설치 앱을 정확히 반영한다."""
    registry.populate(TWO_APPS)

    assert registry.is_installed(f"{PKG}.alpha") is True
    assert registry.is_installed(f"{PKG}.unregistered") is False
    assert registry.get_app_config("alpha").name == f"{PKG}.alpha"
    assert {m.__name__ for m in registry.get_models()} == {"AlphaThing", "BetaThing"}
    assert registry.get_model("alpha", "alphathing").__name__ == "AlphaThing"
    assert registry.get_model("alpha", "AlphaThing").__name__ == "AlphaThing"
