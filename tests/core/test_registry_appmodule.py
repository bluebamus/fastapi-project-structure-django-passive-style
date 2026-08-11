import pytest
from fastapi import APIRouter

from app.core.registry import AppModule


def test_appmodule_router_convention():
    """router_attr 는 <name>_router 컨벤션을 따른다."""
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    assert m.router_attr == "alpha_router"
    assert m.prefix == "/api"


def test_appmodule_load_router_returns_convention_router():
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    router = m.load_router()
    assert isinstance(router, APIRouter)


def test_appmodule_load_router_missing_returns_none():
    """라우터 모듈이 없으면 None(beta 는 router.py 가 없음)."""
    m = AppModule(name="beta", package="tests.core._fakeapps.beta")
    assert m.load_router() is None


def test_appmodule_load_admin_views():
    m = AppModule(name="beta", package="tests.core._fakeapps.beta")
    views = m.load_admin_views()
    assert len(views) == 2


def test_appmodule_load_admin_views_missing_returns_empty():
    m = AppModule(name="alpha", package="tests.core._fakeapps.alpha")
    assert m.load_admin_views() == []


# ---------------------------------------------------------------------------
# 선택 모듈 "부재" 와 그 모듈 "내부 import 실패" 는 다른 사건이다 (계획서 P1-1).
#
# 둘 다 ModuleNotFoundError 라서 통째로 삼키면, 패키지 누락이나 오타 하나로
# 앱의 라우터·모델·Admin 이 조용히 사라진 채 서버가 정상 기동한다. 원인은
# 나중에 "엔드포인트가 없다" / "테이블이 없다" 로만 드러나 추적이 어렵다.
# 아래 gamma 는 세 모듈이 모두 존재하되 내부 import 가 깨진 앱이다.
# ---------------------------------------------------------------------------

_GAMMA = "tests.core._fakeapps.gamma"


def test_load_router_reraises_internal_import_failure():
    """router 모듈은 있는데 그 안의 import 가 실패하면 조용히 넘어가지 않는다."""
    m = AppModule(name="gamma", package=_GAMMA)
    with pytest.raises(ModuleNotFoundError) as exc:
        m.load_router()
    assert exc.value.name == "totally_missing_dependency_xyz"


def test_load_admin_views_reraises_internal_import_failure():
    m = AppModule(name="gamma", package=_GAMMA)
    with pytest.raises(ModuleNotFoundError) as exc:
        m.load_admin_views()
    assert exc.value.name == "totally_missing_dependency_xyz"


def test_import_models_reraises_internal_import_failure():
    m = AppModule(name="gamma", package=_GAMMA)
    with pytest.raises(ModuleNotFoundError) as exc:
        m.import_models()
    assert exc.value.name == "totally_missing_dependency_xyz"


def test_missing_optional_modules_still_return_empty():
    """앱 패키지 자체가 없어도 선택 모듈 조회는 '없음' 으로 처리한다(예외 아님).

    잘못된 앱 이름을 잡는 건 discover() 의 책임이다 — 여기서 예외를 던지면
    같은 결함이 두 곳에서 서로 다른 모양으로 터진다.
    """
    m = AppModule(name="nope", package="tests.core._fakeapps.nope")
    assert m.load_router() is None
    assert m.load_admin_views() == []
    m.import_models()  # 예외 없이 통과
