"""``ADMIN_DISABLED`` — 관리 화면을 끄면 흔적도 없다 (admin-login ADR-005).

끈 관리 화면은 "막혀 있는" 것이 아니라 "없는" 것이어야 한다. 경로가 응답·헤더·로그 어디에도
나오지 않아야 공격자가 위치를 알 수 없다. sqladmin 이 import 되지 않는 것은
``tests/core/test_admin_lazy_loading.py`` 가 깨끗한 프로세스로 본다.

예전 ``ADMIN`` 설정은 뜻이 뒤집혀 이름이 바뀌었다 — 남아 있으면 기동이 멈춘다.
"""

from __future__ import annotations

import logging

import pytest
from httpx import ASGITransport, AsyncClient
from starlette.routing import Mount

from app.core.apps import Apps
from app.core.bootstrap import create_app
from app.core.security import admin_credentials
from app.core.security.dependencies import get_admin_session_store

#: 앱이 응답하는 알려진 경로 — 관리 화면 경로·공개 문서·API(인증 필요·불필요)·없는 경로.
PROBE_PATHS = (
    "/admin",
    "/admin/",
    "/admin/login",
    "/admin/logout",
    "/admin/statics/css/main.css",
    "/",
    "/health",
    "/ready",
    "/docs",
    "/openapi.json",
    "/api/v1/auth/me",
    "/api/v1/home/access-logs",
    "/does-not-exist",
)


@pytest.fixture
def disabled_app(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture):
    """관리 화면을 끈 앱. 자격 확인 팩토리가 불리면 실패한다(백엔드가 조립되면 안 된다)."""

    def _must_not_be_called():
        raise AssertionError("관리 화면을 껐는데 자격 확인이 조립됐다")

    caplog.set_level(logging.INFO, logger="app.core.bootstrap")
    app = create_app(registry=Apps(), admin_disabled=True)
    # ready() 가 등록한 팩토리를 바꿔 둔다 — 이후 조립 시도가 있으면 드러난다.
    monkeypatch.setattr(admin_credentials, "_factory", _must_not_be_called)
    return app


def test_nothing_admin_is_built(disabled_app):
    app = disabled_app

    assert not hasattr(app.state, "admin")
    assert not {"SessionMiddleware", "RedisSessionMiddleware"} & {
        m.cls.__name__ for m in app.user_middleware
    }
    mounts = [r for r in app.routes if isinstance(r, Mount)]
    assert not [m for m in mounts if m.path.startswith("/admin")]


@pytest.mark.parametrize("path", [p for p in PROBE_PATHS if p.startswith("/admin")])
async def test_admin_paths_are_404(disabled_app, path: str):
    async with AsyncClient(transport=ASGITransport(app=disabled_app), base_url="http://test") as c:
        response = await c.get(path)

    assert response.status_code == 404


async def test_no_response_mentions_the_admin_path(disabled_app):
    """본문·헤더 어디에도 ``/admin`` 이 없다 — OpenAPI·/docs(DEBUG)·오류 본문 포함."""
    leaks: list[str] = []
    async with AsyncClient(transport=ASGITransport(app=disabled_app), base_url="http://test") as c:
        for path in PROBE_PATHS:
            response = await c.get(path)
            headers = "\n".join(f"{k}: {v}" for k, v in response.headers.items())
            if "/admin" in response.text or "/admin" in headers:
                leaks.append(f"{path} ({response.status_code})")
            # 경로에 'admin' 을 넣은 요청은 본문에 그 경로를 되돌려 주지 않는다.
            if path.startswith("/admin"):
                assert "admin" not in response.text.lower(), path

    assert not leaks, f"/admin 이 응답에 나온다: {leaks}"


def test_no_admin_session_store_is_built(disabled_app):
    """사용자 기능의 폐기 훅이 받는 저장소가 없다 — 관리 세션이 없으므로 지울 것도 없다."""

    class _Request:
        app = disabled_app

    assert get_admin_session_store(_Request(), redis=object()) is None  # type: ignore[arg-type]


def test_startup_log_does_not_carry_the_path(disabled_app, caplog):
    # 앱은 픽스처(setup 단계)에서 만들어진다.
    records = caplog.get_records("setup")
    messages = [r.getMessage() for r in records if r.name == "app.core.bootstrap"]
    disabled = [m for m in messages if "ADMIN_DISABLED=true" in m]

    assert disabled, "비활성화 로그가 없다"
    assert not [m for m in disabled if "/admin" in m]


# ---------------------------------------------------------------------------
# 예전 ADMIN 설정 — 조용히 무시하지 않는다
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["ADMIN", "admin"])
def test_leftover_admin_in_environment_stops_startup(tmp_path, name: str):
    import config

    with pytest.raises(ValueError, match="ADMIN_DISABLED"):
        config.validate_removed_settings("production", tmp_path / ".env", {name: "false"})


def test_leftover_admin_in_env_file_stops_startup(tmp_path):
    import config

    env_file = tmp_path / ".env"
    env_file.write_text("ENV=development\nADMIN=false\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        config.validate_removed_settings("development", env_file, {})

    assert "ADMIN_DISABLED=true" in str(excinfo.value)


def test_new_name_and_similar_names_pass(tmp_path):
    import config

    env_file = tmp_path / ".env"
    env_file.write_text("ADMIN_DISABLED=true\nADMIN_VIEWS=x\n", encoding="utf-8")

    config.validate_removed_settings("production", env_file, {"ADMIN_DISABLED": "true"})


def test_check_runs_at_config_import(monkeypatch: pytest.MonkeyPatch, restore_config):
    """모듈 import 경로에 검사가 걸려 있다 — 함수만 있고 안 불리면 의미가 없다."""
    import importlib

    from tests.core.test_deployment_safety import SOURCE, STRONG

    monkeypatch.setenv("ENV", "development")
    for key, value in {**SOURCE, **STRONG}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("ADMIN", "false")

    with pytest.raises(ValueError, match="ADMIN_DISABLED"):
        importlib.reload(restore_config)
