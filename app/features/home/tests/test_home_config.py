"""Home 앱 등록은 registry 결선으로 이뤄진다.

sink 등록은 ``HomeConfig.ready()`` hook 이 하고(패키지 import 부수효과가 아니다),
router 는 ``AppConfig`` 가 선언한 컨벤션 경로에서 registry adapter 가 가져간다.
"""


def test_register_sink_installs_home_sink():
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.features.home.access_log_sink import HomeAccessLogSink, register_sink

    original = get_access_log_sink()
    try:
        set_access_log_sink(None)
        register_sink()
        assert isinstance(get_access_log_sink(), HomeAccessLogSink)
    finally:
        set_access_log_sink(original)


def test_home_package_exposes_router_and_main_includes_it():
    from app.core.apps import AppConfig
    from app.features.home.api.routers.router import home_router

    # 패키지가 취합 라우터를 공개한다.
    assert AppConfig.create("app.features.home.apps.HomeConfig").import_router() is home_router

    # main.py 가 /api 프리픽스로 취합한다.
    from main import app

    # app.routes 직접 순회는 FastAPI 버전에 따라 하위 라우터가 평탄화되지 않는다.
    paths = set(app.openapi()["paths"])
    assert any(p.startswith("/api/v1/home") for p in paths)
