import pytest

from app.core.registry import AppRegistry


def test_discover_reads_installed_apps_in_order(monkeypatch):
    """수동 등록: discover 는 config.INSTALLED_APPS 를 목록 순서 그대로 읽는다(정렬 안 함)."""
    import config

    monkeypatch.setattr(config, "INSTALLED_APPS", ["beta", "alpha"])
    reg = AppRegistry()
    apps = reg.discover(package="tests.core._fakeapps")
    assert [a.name for a in apps] == ["beta", "alpha"]  # 목록 순서 보존
    assert reg.enabled_apps == apps
    assert all(a.package.startswith("tests.core._fakeapps.") for a in apps)


def test_discover_uses_real_installed_apps():
    """실제 config.INSTALLED_APPS 에 등록된 도메인 앱들이 발견된다."""
    reg = AppRegistry()
    names = [a.name for a in reg.discover()]
    assert "home" in names
    assert "blog" in names
    assert names[0] == "home"  # INSTALLED_APPS 의 첫 항목(명시적 순서)


# ---------------------------------------------------------------------------
# 수동 등록 방식에서 INSTALLED_APPS 는 유일한 진실 공급원이다(C-9).
# 그 목록이 잘못됐을 때 무엇이 잘못됐는지 즉시 말해주지 않으면, 수동 등록의
# 유일한 비용(직접 적어야 함)만 남고 이점(명시성)이 사라진다.
# ---------------------------------------------------------------------------


def test_discover_rejects_unknown_app_with_explicit_error(monkeypatch):
    """없는 앱 이름은 앱 이름과 기대 패키지 경로를 담은 오류로 바뀐다."""
    import config

    monkeypatch.setattr(config, "INSTALLED_APPS", ["alpha", "ghost"])
    with pytest.raises(ImportError) as exc:
        AppRegistry().discover(package="tests.core._fakeapps")

    message = str(exc.value)
    assert "ghost" in message, "어느 앱이 문제인지 이름이 있어야 한다"
    assert "tests.core._fakeapps.ghost" in message, "어디를 찾았는지 경로가 있어야 한다"
    assert "INSTALLED_APPS" in message, "어디를 고쳐야 하는지 알려야 한다"


def test_discover_reraises_internal_import_failure(monkeypatch):
    """앱 패키지는 있는데 그 내부 import 가 깨진 경우는 원래 오류로 터진다.

    '앱 이름이 틀렸다' 로 오진하면 멀쩡한 INSTALLED_APPS 를 붙잡고 헤매게 된다.
    """
    import config

    monkeypatch.setattr(config, "INSTALLED_APPS", ["broken"])
    with pytest.raises(ModuleNotFoundError) as exc:
        AppRegistry().discover(package="tests.core._fakeapps")
    assert exc.value.name == "totally_missing_dependency_xyz"


def test_discover_rejects_duplicate_apps(monkeypatch):
    """중복 등록은 라우터를 두 번 마운트한다 — 설정 단계에서 막는다."""
    import config

    monkeypatch.setattr(config, "INSTALLED_APPS", ["alpha", "beta", "alpha"])
    with pytest.raises(ValueError) as exc:
        AppRegistry().discover(package="tests.core._fakeapps")
    assert "alpha" in str(exc.value)
