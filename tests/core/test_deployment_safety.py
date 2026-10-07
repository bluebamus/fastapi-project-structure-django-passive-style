"""설정 검증(validate_env_source · validate_deployment_safety).

``ENV`` 가 test 가 아니면(개발 환경 포함) config import 가 다음을 거부해야 한다.

* ``ACCESS_TOKEN_SECRET_KEY``·``REFRESH_TOKEN_SECRET_KEY``·``SESSION_SECRET_KEY`` 중
  placeholder(빈 값, ``your-`` 로 시작, ``change-this`` 포함)가 있는 경우
* access 키와 refresh 키가 같은 경우, 서명·세션 키가 32자 미만인 경우
* `.env` 가 없고 필수 값(``REQUIRED_WITHOUT_ENV_FILE``)이 환경 변수로도 없는 경우

staging/production 은 추가로 debug 모드를 거부한다.

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

# 비밀번호 3종. MySQL 은 빈 값도 위반이고, Redis·SMTP 는 빈 값이 정당한 구성이다.
PASSWORD_KEYS = ("MYSQL_PASSWORD", "REDIS_PASSWORD", "SMTP_PASSWORD")

# 테스트용 강한 값 — 서로 다르고 placeholder 규칙에 걸리지 않는다.
# 비밀번호까지 명시하는 이유: 로컬 `.env` 에 예시값이 남아 있어도 결과가 흔들리지 않게 한다.
STRONG = {
    "ACCESS_TOKEN_SECRET_KEY": "k7Qe2mZ9vX1pL4rT8wY3nB6cH0sD5fGa-access",
    "REFRESH_TOKEN_SECRET_KEY": "Jm3Nq8Rt1Vw6Xy9Za2Bc5De0Fg4Hi7Kl-refresh",
    "SESSION_SECRET_KEY": "Pq9Rs2Tu5Vw8Xy1Za4Bc7De0Fg3Hi6Jk-session",
    "MYSQL_PASSWORD": "Wz4Xa7Bc0De3Fg6Hi9Jk2Lm5No8Pq1Rs-mysql",
    "REDIS_PASSWORD": "Tu6Vw9Xy2Za5Bc8De1Fg4Hi7Jk0Lm3No-redis",
    "SMTP_PASSWORD": "Bc1De4Fg7Hi0Jk3Lm6No9Pq2Rs5Tu8Vw-smtp",
}

# `.env` 가 없는 환경(CI)에서 출처 검증을 통과시키는 나머지 필수 값. 비밀 키·MYSQL_PASSWORD 는
# 각 테스트가 주는 값(대개 STRONG)이 덮어쓴다 — 기본으로 넣어 두지 않으면 `.env` 가 없을 때
# 출처 검증이 먼저 걸려, 내용 검증을 보려는 테스트가 엉뚱한 이유로 실패한다.
SOURCE = {
    "MYSQL_HOST": "127.0.0.1",
    "MYSQL_USER": "app",
    "MYSQL_DATABASE": "app",
    "MYSQL_PASSWORD": "Wz4Xa7Bc0De3Fg6Hi9Jk2Lm5No8Pq1Rs-mysql",
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
        for key, value in {**SOURCE, **values}.items():
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


def test_test_env_is_not_checked(load_config):
    placeholders = dict.fromkeys(SECRET_KEYS, "change-this")
    config_module = load_config("test", placeholders)
    assert config_module.jwt_settings.ACCESS_TOKEN_SECRET_KEY == "change-this"


def test_development_rejects_placeholder_secrets(load_config):
    """기본값·예시 값 그대로는 개발 환경에서도 기동하지 않는다 — `.env` 를 채우라는 신호."""
    placeholders = dict.fromkeys(SECRET_KEYS, "change-this")
    with pytest.raises(ValueError) as excinfo:
        load_config("development", dict(STRONG, **placeholders))
    for key in SECRET_KEYS:
        assert key in str(excinfo.value)


def test_development_rejects_empty_mysql_password(load_config):
    with pytest.raises(ValueError, match="MYSQL_PASSWORD"):
        load_config("development", dict(STRONG, MYSQL_PASSWORD=""))


@pytest.mark.parametrize("env", ["development", "production"])
def test_short_secret_key_is_rejected(load_config, env: str):
    short = "k7Qe2mZ9vX1pL4rT8wY3nB6cH0s"  # 27자
    with pytest.raises(ValueError, match="SESSION_SECRET_KEY") as excinfo:
        load_config(env, dict(STRONG, SESSION_SECRET_KEY=short))
    assert short not in str(excinfo.value)


def test_debug_mode_is_allowed_in_development(load_config):
    config_module = load_config("development", dict(STRONG, DEBUG="true"))
    assert config_module.app_settings.DEBUG is True


def _import_config_in_subprocess(values: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "ENV": "production",
        "ADMIN": "false",
        "LOG_SQL_ECHO_ENABLED": "false",
        "DEBUG": "false",
        **SOURCE,
        **values,
    }
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


# =============================================================================
# 비밀번호 3종 — `.env.example` 예시값과 빈 값 판단
# =============================================================================
def test_env_example_passwords_are_rejected_in_production(load_config):
    """`.env.example` 의 비밀번호 예시값도 그대로 운영에 들고 가면 기동이 실패한다."""
    values = _env_example_values()
    for key in PASSWORD_KEYS:
        assert key in values, f".env.example 에 {key} 가 없다"
    values["ENV"] = "production"
    values["ADMIN"] = "false"

    with pytest.raises(ValueError) as excinfo:
        load_config("production", values)

    message = str(excinfo.value)
    for key in ("MYSQL_PASSWORD", "SMTP_PASSWORD"):
        assert key in message, f"{key} 예시값이 placeholder 판정에 걸리지 않는다"
        assert values[key] not in message, "오류 메시지에 비밀값이 실렸다"
    # `.env.example` 의 REDIS_PASSWORD 는 비어 있다 — 인증 없는 Redis 는 정당하다.
    assert "REDIS_PASSWORD" not in message


@pytest.mark.parametrize("placeholder", ["your-password", "x-change-this-x", "  YOUR-Db-Pw  "])
@pytest.mark.parametrize("key", PASSWORD_KEYS)
def test_password_placeholders_are_rejected(load_config, key: str, placeholder: str):
    """값이 들어 있는데 예시값 모양이면 세 비밀번호 모두 기동을 거부한다."""
    with pytest.raises(ValueError, match=key):
        load_config("production", dict(STRONG, **{key: placeholder}))


def test_empty_mysql_password_is_rejected(load_config):
    """MySQL 은 빈 값도 위반이다 — 운영 DB 에 비밀번호 없이 붙는 것 자체가 사고다."""
    with pytest.raises(ValueError, match="MYSQL_PASSWORD"):
        load_config("production", dict(STRONG, MYSQL_PASSWORD=""))


@pytest.mark.parametrize("key", ["REDIS_PASSWORD", "SMTP_PASSWORD"])
def test_empty_optional_passwords_are_allowed(load_config, key: str):
    """인증 없는 Redis·SMTP 미사용은 정당한 구성이라 빈 값을 위반으로 보지 않는다.

    여기서 빈 값을 막으면 멀쩡한 배포가 기동하지 못한다 — `REDIS_URL` 은 비밀번호가
    없으면 인증 없는 URL 을 만들도록 이미 분기하고, SMTP 는 발송 모듈이 없으면 쓰이지
    않는다. 값이 들어 있을 때만 예시값인지 본다.
    """
    config_module = load_config("production", dict(STRONG, **{key: ""}))

    assert config_module.app_settings.ENV == "production"


# =============================================================================
# 설정의 출처 — `.env` 가 없으면 필수 값이 환경 변수로 와야 한다
# =============================================================================
FULL_ENVIRON = {"ENV": "production", **STRONG, **SOURCE}


def test_missing_env_file_without_environ_is_rejected(tmp_path):
    import config as config_module

    with pytest.raises(ValueError) as excinfo:
        config_module.validate_env_source("development", tmp_path / ".env", {})
    message = str(excinfo.value)
    assert ".env" in message
    for name in config_module.REQUIRED_WITHOUT_ENV_FILE:
        assert name in message


def test_missing_env_file_names_only_what_is_missing(tmp_path):
    import config as config_module

    environ = {k: v for k, v in FULL_ENVIRON.items() if k != "MYSQL_PASSWORD"}
    with pytest.raises(ValueError) as excinfo:
        config_module.validate_env_source("production", tmp_path / ".env", environ)
    message = str(excinfo.value)
    assert "MYSQL_PASSWORD" in message
    assert "MYSQL_HOST" not in message
    for value in environ.values():
        assert value not in message


def test_injected_environ_without_env_file_passes(tmp_path):
    """컨테이너처럼 파일 없이 환경 변수로 모두 주입하면 통과한다."""
    import config as config_module

    config_module.validate_env_source("production", tmp_path / ".env", FULL_ENVIRON)


def test_existing_env_file_passes(tmp_path):
    import config as config_module

    env_file = tmp_path / ".env"
    env_file.write_text("ENV=development\n", encoding="utf-8")
    config_module.validate_env_source("development", env_file, {})


def test_test_env_skips_source_check(tmp_path):
    import config as config_module

    config_module.validate_env_source("test", tmp_path / ".env", {})


def test_import_fails_without_env_file_and_environ(tmp_path):
    """검증은 import 시점에 실제로 돈다 — `.env` 없는 작업 디렉터리, 필수 값 없음."""
    import config as config_module

    env = {
        k: v
        for k, v in os.environ.items()
        if k not in config_module.REQUIRED_WITHOUT_ENV_FILE and k != "PYTHONPATH"
    }
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(  # noqa: S603 - 인터프리터·코드가 이 파일에 고정돼 있다
        [sys.executable, "-X", "utf8", "-c", "import config"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode != 0
    assert ".env 파일이 없고" in result.stderr


def test_deployed_admin_with_ack_logs_warning_on_startup():
    """승인(ADMIN_UNAUTHENTICATED_ACK)으로 연 /admin 은 기동마다 WARNING 을 남긴다."""
    env = dict(
        os.environ,
        **FULL_ENVIRON,
        ADMIN="true",
        ADMIN_UNAUTHENTICATED_ACK="true",
        LOG_SQL_ECHO_ENABLED="false",
        DEBUG="false",
        LOG_LEVEL="INFO",
    )
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(  # noqa: S603 - 인터프리터·코드가 이 파일에 고정돼 있다
        [sys.executable, "-X", "utf8", "-c", "import main"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    output = result.stdout + result.stderr
    assert "WARNING" in output
    assert "SQLAdmin 이 인증 없이 열려 있습니다" in output
