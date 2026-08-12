"""AC-01 — 등록 항목 정규화와 기본 config 선택 규칙 (FR-02·FR-03·CR-01·CR-02).

``INSTALLED_APPS`` 항목은 package 경로든 explicit config class 경로든 **같은
``AppConfig`` 인스턴스**로 정규화되어야 한다. 이 파일은 Django 의 config 선택 규칙
(0개·1개·복수+default) 네 갈래를 전부 고정한다.
"""

from pathlib import Path

import pytest

from app.core.apps import AppConfig
from app.core.apps.exceptions import ImproperlyConfigured

PKG = "tests.core.apps._fixtures"


def test_package_entry_and_class_entry_produce_equivalent_config():
    """package 경로와 config class 경로가 같은 정규화 결과를 낸다."""
    from_package = AppConfig.create(f"{PKG}.alpha")
    from_class = AppConfig.create(f"{PKG}.alpha.apps.AlphaConfig")

    assert type(from_package) is type(from_class)
    assert from_package.name == from_class.name == f"{PKG}.alpha"
    assert from_package.label == from_class.label == "alpha"
    assert from_package.path == from_class.path


def test_config_exposes_django_public_attributes():
    """FR-03: name·label·verbose_name·path·module 이 모두 채워진다."""
    config = AppConfig.create(f"{PKG}.alpha")

    assert config.name == f"{PKG}.alpha"
    assert config.label == "alpha"
    assert config.verbose_name == "Alpha"
    assert isinstance(config.path, Path)
    assert config.path.is_dir()
    assert config.module.__name__ == f"{PKG}.alpha"


def test_package_without_apps_module_gets_base_config():
    """CR-01: config 가 0개면 기본 ``AppConfig`` 를 만든다."""
    config = AppConfig.create(f"{PKG}.plain")

    assert type(config) is AppConfig
    assert config.label == "plain"


def test_single_config_is_selected():
    """CR-01: config 가 1개면 그것을 선택한다."""
    config = AppConfig.create(f"{PKG}.alpha")

    assert type(config).__name__ == "AlphaConfig"


def test_multiple_configs_select_the_single_default_true():
    """CR-01: 복수 config 중 ``default=True`` 하나만 선택한다."""
    config = AppConfig.create(f"{PKG}.multi_default")

    assert type(config).__name__ == "PrimaryConfig"
    assert config.label == "multi_primary"


def test_only_config_marked_default_false_falls_back_to_base():
    """CR-01: ``default=False`` 는 자동 선택 후보에서 빠진다."""
    config = AppConfig.create(f"{PKG}.default_false")

    assert type(config) is AppConfig
    assert config.label == "default_false"


def test_ambiguous_configs_are_rejected():
    """CR-01: 선택 규칙으로 결정할 수 없으면 실패한다."""
    with pytest.raises(ImproperlyConfigured) as exc:
        AppConfig.create(f"{PKG}.ambiguous")

    message = str(exc.value)
    assert f"{PKG}.ambiguous.apps" in message
    assert "default = True" in message


def test_router_attribute_defaults_to_label_router():
    """§6.2: ``router_attribute`` 기본값은 ``<label>_router`` 다."""
    assert AppConfig.create(f"{PKG}.alpha").router_attribute == "alpha_router"
