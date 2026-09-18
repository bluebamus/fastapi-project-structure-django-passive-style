"""운영·스테이징 기동 시 서명/세션 비밀키 검증(validate_deployment_safety).

``ENV`` 가 staging/production 이면 config import 가 다음을 거부해야 한다.

* ``ACCESS_TOKEN_SECRET_KEY``·``REFRESH_TOKEN_SECRET_KEY``·``SESSION_SECRET_KEY`` 중
  placeholder(빈 값, ``your-`` 로 시작, ``change-this`` 포함)가 있는 경우
* access 키와 refresh 키가 같은 경우

위반은 한 번의 예외에 **모두** 모아 설정 **이름만** 알린다 — 값은 로그로 새면 안 된다.
"""

from __future__ import annotations

import importlib
import os
import re
import subprocess  # noqa: S404 - config import 자체가 실패하는지 자식 프로세스로 본다
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SECRET_KEYS = ("ACCESS_TOKEN_SECRET_KEY", "REFRESH_TOKEN_SECRET_KEY", "SESSION_SECRET_KEY")

# 테스트용 강한 값 — 서로 다르고 placeholder 규칙에 걸리지 않는다.
STRONG = {
    "ACCESS_TOKEN_SECRET_KEY": "k7Qe2mZ9vX1pL4rT8wY3nB6cH0sD5fGa-access",
    "REFRESH_TOKEN_SECRET_KEY": "Jm3Nq8Rt1Vw6Xy9Za2Bc5De0Fg4Hi7Kl-refresh",
    "SESSION_SECRET_KEY": "Pq9Rs2Tu5Vw8Xy1Za4Bc7De0Fg3Hi6Jk-session",
}


def _env_example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


@pytest.fixture
def load_config(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    """환경변수를 덮어쓰고 config 를 다시 import 한다. 끝나면 원상 복구.

    reload 는 같은 모듈 dict 에 새 설정 객체를 채운다. 다른 테스트 모듈이 수집 시점에
    잡아 둔 ``db_settings`` 등과 어긋나지 않도록, 끝나면 원래 객체로 되돌린다.
    """
    import config as config_module

    snapshot = dict(vars(config_module))

    def _load(env: str, values: dict[str, str]) -> object:
        monkeypatch.setenv("ENV", env)
        # 다른 운영 가드(무인증 /admin, SQL echo, debug 모드)를 비켜 검증 대상에 도달시킨다.
        # pytest 는 DEBUG=true 로 돌기 때문에(pyproject `env`) 명시적으로 꺼 준다.
        monkeypatch.setenv("ADMIN", "false")
        monkeypatch.setenv("LOG_SQL_ECHO_ENABLED", "false")
        monkeypatch.setenv("DEBUG", "false")
        for key, value in values.items():
            monkeypatch.setenv(key, value)
        return importlib.reload(config_module)

    yield _load

    monkeypatch.undo()
    vars(config_module).clear()
    vars(config_module).update(snapshot)


def test_env_example_secrets_are_rejected_in_production(load_config):
    """`.env.example` 을 그대로 운영에 들고 가면 기동이 실패하고, 세 키를 모두 알린다."""
    values = _env_example_values()
    for key in SECRET_KEYS:
        assert key in values, f".env.example 에 {key} 가 없다"
    values["ENV"] = "production"
    values["ADMIN"] = "false"

    with pytest.raises(ValueError) as excinfo:
        load_config("production", values)

    message = str(excinfo.value)
    for key in SECRET_KEYS:
        assert key in message
        assert values[key] not in message, "오류 메시지에 비밀값이 실렸다"


@pytest.mark.parametrize("env", ["production", "staging"])
def test_distinct_strong_secrets_pass(load_config, env: str):
    config_module = load_config(env, STRONG)
    assert config_module.app_settings.ENV == env


@pytest.mark.parametrize("env", ["production", "staging"])
def test_equal_access_and_refresh_keys_are_rejected(load_config, env: str):
    same = dict(STRONG, REFRESH_TOKEN_SECRET_KEY=STRONG["ACCESS_TOKEN_SECRET_KEY"])

    with pytest.raises(ValueError) as excinfo:
        load_config(env, same)

    message = str(excinfo.value)
    assert "ACCESS_TOKEN_SECRET_KEY" in message
    assert "REFRESH_TOKEN_SECRET_KEY" in message
    assert "SESSION_SECRET_KEY" not in message
    assert STRONG["ACCESS_TOKEN_SECRET_KEY"] not in message


@pytest.mark.parametrize(
    "placeholder",
    [
        "your-secret-key",
        "  YOUR-Access-Key  ",
        "prefix-change-this-suffix",
        "CHANGE-THIS",
        "",
        "   ",
    ],
)
@pytest.mark.parametrize("key", SECRET_KEYS)
def test_placeholder_variants_are_rejected(load_config, key: str, placeholder: str):
    values = dict(STRONG, **{key: placeholder})

    with pytest.raises(ValueError, match=key):
        load_config("production", values)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("your-key", True),
        (" Your-key", True),
        ("x-change-this-x", True),
        ("", True),
        ("  ", True),
        ("my-your-key", False),
        (STRONG["SESSION_SECRET_KEY"], False),
    ],
)
def test_is_placeholder_secret(value: str, expected: bool):
    from config import is_placeholder_secret

    assert is_placeholder_secret(value) is expected


@pytest.mark.parametrize("env", ["production", "staging"])
def test_debug_mode_is_rejected_in_deployment(load_config, env: str):
    """``DEBUG=true`` 는 유효 로그 레벨을 DEBUG 로 만든다 — 배포에서는 기동을 거부한다."""
    with pytest.raises(ValueError, match="DEBUG"):
        load_config(env, dict(STRONG, DEBUG="true"))


@pytest.mark.parametrize("env", ["production", "staging"])
def test_debug_log_level_is_rejected_in_deployment(load_config, env: str):
    """``DEBUG=false`` 라도 ``LOG_LEVEL=debug`` 면 같은 결과가 된다 — 역시 거부한다."""
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        load_config(env, dict(STRONG, LOG_LEVEL="debug"))


@pytest.mark.parametrize("env", ["development", "test"])
def test_development_and_test_are_not_checked(load_config, env: str):
    placeholders = dict.fromkeys(SECRET_KEYS, "change-this")
    config_module = load_config(env, placeholders)
    assert config_module.jwt_settings.ACCESS_TOKEN_SECRET_KEY == "change-this"


def _import_config_in_subprocess(values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = dict(
        os.environ,
        ENV="production",
        ADMIN="false",
        LOG_SQL_ECHO_ENABLED="false",
        DEBUG="false",
        **values,
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(  # noqa: S603 - 인터프리터·코드가 이 파일에 고정돼 있다
        [sys.executable, "-X", "utf8", "-c", "import config"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def test_check_runs_at_import_time():
    """검증은 호출을 잊을 수 없도록 config import 시점에 돈다."""
    placeholders = {
        "ACCESS_TOKEN_SECRET_KEY": "change-this-access-token-secret-key",
        "REFRESH_TOKEN_SECRET_KEY": "change-this-refresh-token-secret-key",
        "SESSION_SECRET_KEY": "change-this-session-secret-key",
    }
    failed = _import_config_in_subprocess(placeholders)
    assert failed.returncode != 0
    for key in SECRET_KEYS:
        assert key in failed.stderr
    for value in placeholders.values():
        assert value not in failed.stderr

    ok = _import_config_in_subprocess(STRONG)
    assert ok.returncode == 0, ok.stderr
