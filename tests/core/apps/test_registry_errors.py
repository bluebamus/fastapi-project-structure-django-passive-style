"""AC-03 — 잘못된 등록의 실패 계약 (CR-04·CR-06·NFR-07·SEC-07).

수동 등록의 값어치는 "틀리면 즉시, 어디를 고칠지와 함께 터진다" 는 데 있다. 오류
메시지에 **문제가 된 entry·이름·시도한 dotted path** 가 없으면 계약 위반으로 본다.
"""

import pytest

from app.core.apps import Apps
from app.core.apps.exceptions import (
    AppRegistryNotReady,
    ImproperlyConfigured,
)

PKG = "tests.core.apps._fixtures"


def test_missing_package_reports_the_attempted_path(registry: Apps):
    """없는 package 는 시도한 dotted path 를 담아 실패한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.does_not_exist"])

    assert f"{PKG}.does_not_exist" in str(exc.value)
    assert "INSTALLED_APPS" in str(exc.value)


def test_config_class_that_is_not_appconfig_is_rejected(registry: Apps):
    """CR-02: ``AppConfig`` subclass 가 아니면 거부한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.eventlog.record"])

    assert "AppConfig" in str(exc.value)


def test_missing_config_class_attribute_is_rejected(registry: Apps):
    """config module 은 있는데 class 이름이 틀린 경우."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.alpha.apps.NoSuchConfig"])

    assert "NoSuchConfig" in str(exc.value)
    assert f"{PKG}.alpha.apps" in str(exc.value)


def test_duplicate_entries_are_rejected(registry: Apps):
    """같은 항목을 두 번 적으면 실패한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.alpha", f"{PKG}.alpha"])

    assert "중복" in str(exc.value)


def test_duplicate_label_is_rejected(registry: Apps):
    """CR-04: 서로 다른 앱이 같은 label 을 쓰면 실패한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.alpha", f"{PKG}.dup_label"])

    assert "label" in str(exc.value)
    assert "alpha" in str(exc.value)


def test_duplicate_name_is_rejected(registry: Apps):
    """CR-04: 같은 package 를 다른 config 로 두 번 등록하면 실패한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate(
            [
                f"{PKG}.multi_default.apps.PrimaryConfig",
                f"{PKG}.multi_default.apps.SecondaryConfig",
            ]
        )

    assert "name" in str(exc.value)
    assert f"{PKG}.multi_default" in str(exc.value)


def test_invalid_label_is_rejected(registry: Apps):
    """CR-04: label 은 유효한 Python identifier 여야 한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        registry.populate([f"{PKG}.badlabel"])

    assert "not-an-identifier" in str(exc.value)


def test_lookup_before_population_raises(registry: Apps):
    """CR-06: 준비되지 않은 registry 조회는 명시적 예외다."""
    with pytest.raises(AppRegistryNotReady):
        registry.get_app_configs()
    with pytest.raises(AppRegistryNotReady):
        registry.get_models()


def test_unknown_label_and_model_do_not_return_none(registry: Apps):
    """CR-06: 조회 실패를 조용히 ``None`` 으로 바꾸지 않는다."""
    registry.populate([f"{PKG}.alpha"])

    with pytest.raises(LookupError) as exc:
        registry.get_app_config("nope")
    assert "nope" in str(exc.value)

    with pytest.raises(LookupError) as exc:
        registry.get_model("alpha", "NoSuchModel")
    assert "NoSuchModel" in str(exc.value)


def test_failed_population_leaves_no_partially_ready_state(registry: Apps):
    """NFR-04: 실패 후 registry 에 부분 상태가 남지 않는다."""
    with pytest.raises(ImproperlyConfigured):
        registry.populate([f"{PKG}.alpha", f"{PKG}.does_not_exist"])

    assert (registry.apps_ready, registry.models_ready, registry.ready) == (False, False, False)
    with pytest.raises(AppRegistryNotReady):
        registry.get_app_configs()
