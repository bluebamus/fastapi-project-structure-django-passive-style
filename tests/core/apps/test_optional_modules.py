"""AC-05 — 선택 모듈 부재와 내부 import 실패의 구분 (NFR-03·SEC-07).

이 구분이 무너지면 오타 하나가 "그 앱은 라우터가 없나 보다" 로 조용히 흡수된다.
판정 기준은 ``ModuleNotFoundError.name`` 이다 — 찾던 모듈 자신이 없으면 부재,
그 모듈이 **다른 무언가** 를 못 찾은 것이면 구현 오류다.
"""

import pytest

from app.core.apps import AppConfig, Apps

PKG = "tests.core.apps._fixtures"


def test_app_without_models_is_allowed(registry: Apps):
    """models 가 없는 앱은 정상이다(예: 기준 저장소의 auth)."""
    registry.populate([f"{PKG}.plain"])

    assert registry.get_app_config("plain").get_models() == []
    assert registry.get_models() == []


def test_app_without_router_or_admin_is_allowed():
    """선택 모듈 부재는 ``None`` 으로 관측된다 — 예외가 아니다."""
    config = AppConfig.create(f"{PKG}.plain")

    assert config.import_router() is None
    assert config.import_admin_views() is None


def test_internal_import_error_in_root_package_propagates(registry: Apps):
    """SEC-07: root package 내부의 import 실패는 startup 실패다."""
    with pytest.raises(ModuleNotFoundError) as exc:
        registry.populate([f"{PKG}.broken"])

    assert exc.value.name == "totally_missing_dependency_xyz"


def test_internal_import_error_in_models_propagates(registry: Apps):
    """SEC-07: models 모듈 내부의 import 실패도 startup 실패다."""
    with pytest.raises(ModuleNotFoundError) as exc:
        registry.populate([f"{PKG}.broken_models"])

    assert exc.value.name == "another_missing_dependency_xyz"


def test_internal_import_error_preserves_traceback(registry: Apps):
    """NFR-03: 원래 예외의 type·cause·traceback 을 보존한다."""
    with pytest.raises(ModuleNotFoundError) as exc:
        registry.populate([f"{PKG}.broken"])

    frames = []
    tb = exc.value.__traceback__
    while tb is not None:
        frames.append(tb.tb_frame.f_code.co_filename)
        tb = tb.tb_next
    assert any("broken" in f for f in frames), "실패한 fixture 의 프레임이 사라졌다"
