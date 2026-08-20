"""E 게이트 — default 구현 피드백 보안 하드닝 (development-plan §10.1 E).

sibling 저장소(`fastapi-default-project-structure`)에서 실제로 터진 결함들을
이 저장소 착수 게이트로 이관한 것이다. 네 가지를 기계로 고정한다.

1. SQL 본문·바인딩 파라미터가 **어떤 handler 로도** 새지 않는다 (C-5).
2. alembic 실행이 앱 로거를 죽이지 않는다.
3. `.env.example` 을 그대로 `.env` 로 써도 기동한다.
4. 운영에서 인증 없는 `/admin` 이 사고로 열리지 않는다.
"""

from __future__ import annotations

import importlib
import logging
import re
import subprocess  # noqa: S404 - 자식 프로세스로 alembic 로깅 설정 후 로거 생존을 본다
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 로그에 절대 나타나면 안 되는 값. 실제 유출을 흉내내는 카나리아다.
SECRET_CANARY = "s3cr3t-canary-do-not-log-9f2b"


# =============================================================================
# 1. SQL 유출 차단 (C-5)
# =============================================================================
def _sql_record(logger_name: str, level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name=logger_name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )


@pytest.mark.parametrize(
    "logger_name",
    ["sqlalchemy.engine.Engine", "aiomysql", "aiosqlite", "pymysql", "sqlalchemy.pool"],
)
def test_sql_bind_parameters_are_filtered(logger_name: str):
    """드라이버·ORM 이 찍는 DEBUG/INFO SQL 로그는 통과하지 못한다."""
    from app.utils.logs.filters import SqlNoiseFilter

    sql_filter = SqlNoiseFilter(allow_sql_echo=False)

    for level in (logging.DEBUG, logging.INFO):
        record = _sql_record(logger_name, level, f"INSERT ... ({SECRET_CANARY!r},)")
        assert not sql_filter.filter(record), (
            f"{logger_name} 의 {logging.getLevelName(level)} SQL 로그가 통과했다 — "
            "바인딩 값이 그대로 샌다"
        )


@pytest.mark.parametrize("logger_name", ["sqlalchemy.engine.Engine", "aiomysql", "pymysql"])
def test_sql_warnings_and_errors_survive(logger_name: str):
    """WARNING 이상은 남긴다 — 연결 실패·데드락까지 지우면 장애 때 눈이 먼다."""
    from app.utils.logs.filters import SqlNoiseFilter

    sql_filter = SqlNoiseFilter(allow_sql_echo=False)

    for level in (logging.WARNING, logging.ERROR):
        assert sql_filter.filter(_sql_record(logger_name, level, "lost connection"))


def test_application_logs_are_not_swallowed():
    """앱 로그는 필터에 걸리지 않는다 — 과차단도 결함이다."""
    from app.utils.logs.filters import SqlNoiseFilter

    sql_filter = SqlNoiseFilter(allow_sql_echo=False)
    assert sql_filter.filter(_sql_record("app.features.blog", logging.DEBUG, "hello"))


def test_sql_echo_switch_opens_it_explicitly():
    """개발자가 명시적으로 켜면 보인다 — 디버깅 경로를 없애지는 않는다."""
    from app.utils.logs.filters import SqlNoiseFilter

    sql_filter = SqlNoiseFilter(allow_sql_echo=True)
    assert sql_filter.filter(_sql_record("sqlalchemy.engine.Engine", logging.INFO, "SELECT 1"))


def test_every_handler_has_the_sql_filter():
    """handler 하나라도 빠지면 그 경로로 그대로 샌다."""
    from app.utils.logs.config import build_dictconfig

    config = build_dictconfig()
    assert config["handlers"], "handler 가 하나도 없다 — 검사가 헛통과한다"

    missing = [
        name
        for name, handler in config["handlers"].items()
        if "sql_noise" not in handler.get("filters", [])
    ]
    assert not missing, f"sql_noise 필터가 빠진 handler: {missing}"


# =============================================================================
# 2. alembic 실행 후 앱 로거 생존
# =============================================================================
_LOGGER_SURVIVAL_PROBE = """
import logging
from logging.config import fileConfig

survivor = logging.getLogger("app.probe")
survivor.info("before")

fileConfig("alembic.ini", disable_existing_loggers=False)

print("__RESULT__" + str(survivor.disabled))
"""


def test_alembic_logging_config_keeps_app_loggers_alive():
    """``fileConfig`` 기본값(disable_existing_loggers=True)이면 앱 로깅이 조용히 죽는다."""
    proc = subprocess.run(  # noqa: S603 - 인터프리터·스크립트가 이 파일에 고정돼 있다
        [sys.executable, "-X", "utf8", "-c", _LOGGER_SURVIVAL_PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=120,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    line = next(x for x in proc.stdout.splitlines() if x.startswith("__RESULT__"))
    assert (
        line.removeprefix("__RESULT__") == "False"
    ), "alembic 로깅 설정이 기존 로거를 비활성화했다"


def test_migrations_env_passes_disable_existing_loggers():
    """실제 ``migrations/env.py`` 가 그 인자를 넘긴다."""
    source = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "disable_existing_loggers=False" in source


# =============================================================================
# 3. `.env.example` 이 실제로 로드된다
# =============================================================================
def _env_example_values() -> dict[str, str]:
    """주석이 아닌 실제 설정 줄만 뽑는다 — 사용자가 복사하면 이대로 적용된다."""
    values: dict[str, str] = {}
    for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def test_env_example_passes_settings_validation(monkeypatch: pytest.MonkeyPatch):
    """`.env.example` 을 그대로 `.env` 로 써도 Settings 검증을 통과한다.

    통과하지 못하면 "복사해서 시작하세요"라는 안내가 곧바로 기동 실패로 이어진다.
    실제로 CORS wildcard + credentials 조합이 그 상태였다.
    """
    values = _env_example_values()
    assert values, ".env.example 파싱 결과가 비었다 — 검사가 헛통과한다"

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    import config as config_module

    importlib.reload(config_module)
    try:
        assert config_module.app_settings is not None
    finally:
        # 다른 테스트가 오염된 설정을 보지 않도록 되돌린다.
        for key in values:
            monkeypatch.delenv(key, raising=False)
        importlib.reload(config_module)


# =============================================================================
# 4. 운영에서 인증 없는 /admin 차단
# =============================================================================
@pytest.mark.parametrize("env", ["production", "staging"])
def test_unauthenticated_admin_is_rejected_in_production(env: str):
    """개발 기본값(ADMIN=true)을 그대로 배포하면 기동이 실패한다."""
    from config import AppSettings

    with pytest.raises(ValidationError, match="ADMIN_UNAUTHENTICATED_ACK"):
        AppSettings(ENV=env, ADMIN=True, ADMIN_UNAUTHENTICATED_ACK=False)


@pytest.mark.parametrize("env", ["production", "staging"])
def test_explicit_choices_are_allowed(env: str):
    """끄거나(false) 승인하거나(ack) — 명시적으로 고르면 통과한다."""
    from config import AppSettings

    assert AppSettings(ENV=env, ADMIN=False).ADMIN is False
    assert AppSettings(ENV=env, ADMIN=True, ADMIN_UNAUTHENTICATED_ACK=True).ADMIN is True


@pytest.mark.parametrize("env", ["development", "test"])
def test_development_default_is_untouched(env: str):
    """개발 기본값은 그대로다 — 받자마자 /admin 을 쓸 수 있어야 한다(2026-08-12 결정)."""
    from config import AppSettings

    assert AppSettings(ENV=env, ADMIN=True).ADMIN is True


def test_admin_residual_risk_is_documented():
    """인증 없는 /admin 의 잔여 위험이 운영 문서에 남아 있다."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    assert "인증이 없습니다" in env_example
    assert "ADMIN_UNAUTHENTICATED_ACK" in env_example


# =============================================================================
# 1-b. 실제 유출 probe — 필터 단위 검사만으로는 "실제로 안 샌다"를 증명하지 못한다
# =============================================================================
@pytest.mark.asyncio
async def test_secret_bind_value_never_reaches_handlers(tmp_path: Path):
    """진짜 SQLAlchemy 엔진에 secret 을 bind 해 실행하고, 핸들러 출력을 뒤진다.

    ``echo=True`` 로 SQLAlchemy 가 SQL 과 바인딩 값을 실제로 찍게 만든 다음,
    root 에 붙은 핸들러가 그것을 받는지 본다. 필터가 빠지거나 순서가 틀리면
    카나리아가 출력에 나타난다.
    """
    import io

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.utils.logs.filters import ContextFilter, SqlNoiseFilter

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)
    # 운영 dictConfig 와 같은 순서로 붙인다.
    handler.addFilter(SqlNoiseFilter(allow_sql_echo=False))
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)

    # SQLAlchemy 는 echo 설정을 로거 레벨로 옮긴다 — 테스트 뒤 되돌린다.
    touched = ["sqlalchemy.engine.Engine", "aiosqlite"]
    saved = {name: logging.getLogger(name).level for name in touched}
    for name in touched:
        logging.getLogger(name).setLevel(logging.DEBUG)

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'probe.sqlite3'}", echo=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE probe (secret TEXT)"))
            await connection.execute(
                text("INSERT INTO probe (secret) VALUES (:secret)"),
                {"secret": SECRET_CANARY},
            )
            await connection.execute(
                text("SELECT secret FROM probe WHERE secret = :secret"),
                {"secret": SECRET_CANARY},
            )
    finally:
        await engine.dispose()
        root.removeHandler(handler)
        root.setLevel(previous_level)
        for name, level in saved.items():
            logging.getLogger(name).setLevel(level)

    output = buffer.getvalue()
    assert SECRET_CANARY not in output, "바인딩된 secret 이 로그 핸들러에 도달했다:\n" + "\n".join(
        line for line in output.splitlines() if SECRET_CANARY in line
    )


# =============================================================================
# 1-c. traceback·예외 인자까지 — 최종 formatter 출력 기준
# =============================================================================
def test_log_messages_do_not_interpolate_exception_values():
    """앱 로거가 예외 **메시지**를 그대로 찍지 않는다.

    ``sql_noise`` 필터는 **로거 이름**으로 SQL 소음을 막는다. 그런데 앱 로거
    (`app.core.*`)가 ``logger.error(f"...: {e}")`` 로 DB 예외를 찍으면 그 줄은
    이름이 `app.*` 이라 필터를 그대로 통과한다 — 필터로 막아둔 값이 옆문으로 나간다.
    그래서 예외는 **타입만** 남긴다.
    """
    offenders: list[str] = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "logger." not in line:
                continue
            if "{e}" in line or "{exc}" in line or line.rstrip().endswith(", e)"):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{number}: {line.strip()}")

    assert not offenders, f"로그가 예외 메시지를 그대로 찍는다: {offenders}"


def test_repository_exceptions_do_not_carry_db_message():
    """Repository 예외의 ``detail`` 은 응답으로 나간다 — 원본 DB 메시지를 담으면 안 된다.

    중복 키 하나로 실행된 SQL 과 바인딩된 값이 API 클라이언트에게 전달되던 경로다.
    """
    source = (REPO_ROOT / "app" / "core" / "repositories" / "repository_base.py").read_text(
        encoding="utf-8"
    )
    code_lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
    offenders = [line.strip() for line in code_lines if "str(e)" in line or "str(e.orig)" in line]
    assert not offenders, f"예외 detail 에 원본 DB 메시지가 실린다: {offenders}"


def test_internal_error_response_is_opaque_even_in_debug():
    """DEBUG 에서도 일반 500 응답에 ``str(exc)`` 를 싣지 않는다.

    잡히지 않은 예외 대부분은 DB 계층에서 온다. SQLAlchemy 의 ``str(exc)`` 에는
    실행 SQL 과 바인딩 값, 때로는 DSN 이 들어 있다 — 로그 필터로 막아둔 것을
    응답 경로로 여는 셈이 된다.
    """
    source = (REPO_ROOT / "app" / "core" / "bootstrap.py").read_text(encoding="utf-8")

    # 주석에는 "왜 안 싣는가"를 설명하며 str(exc) 가 나온다 — 코드 줄만 본다.
    code_lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
    offenders = [line.strip() for line in code_lines if "str(exc)" in line]
    assert not offenders, f"bootstrap 에 str(exc) 노출 경로가 남아 있다: {offenders}"

    from fastapi.testclient import TestClient

    from app.core.bootstrap import create_app

    app = create_app()

    @app.get("/__probe_boom")
    async def _boom() -> None:
        raise RuntimeError(f"SELECT * FROM users WHERE token = '{SECRET_CANARY}'")

    # context manager 를 쓰지 않는다 — lifespan 이 돌면 실제 DB 에 붙으려 한다.
    # 여기서 볼 것은 예외 핸들러의 응답 형태뿐이다.
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__probe_boom")

    assert response.status_code == 500
    body = response.text
    assert SECRET_CANARY not in body, f"500 응답에 secret 이 실렸다: {body}"
    assert response.json()["detail"] is None


@pytest.mark.parametrize("env", ["production", "staging"])
def test_sql_echo_is_rejected_in_production(env: str, monkeypatch: pytest.MonkeyPatch):
    """운영에서 ``LOG_SQL_ECHO_ENABLED=true`` 는 기동을 거부한다."""
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("LOG_SQL_ECHO_ENABLED", "true")
    # 운영에서는 무인증 /admin 가드가 먼저 걸린다(F-007). 그것을 통과시켜야
    # 이 테스트가 보려는 SQL echo 검증에 도달한다.
    monkeypatch.setenv("ADMIN", "false")

    import config as config_module

    with pytest.raises(ValueError, match="LOG_SQL_ECHO_ENABLED"):
        importlib.reload(config_module)

    # 오염된 설정을 남기지 않는다.
    for key in ("ENV", "LOG_SQL_ECHO_ENABLED", "ADMIN"):
        monkeypatch.delenv(key, raising=False)
    importlib.reload(config_module)


@pytest.mark.parametrize("env", ["development", "test"])
def test_sql_echo_is_allowed_in_development(env: str, monkeypatch: pytest.MonkeyPatch):
    """개발·테스트에서는 열 수 있다 — 디버깅 경로를 없애지는 않는다."""
    monkeypatch.setenv("ENV", env)
    monkeypatch.setenv("LOG_SQL_ECHO_ENABLED", "true")

    import config as config_module

    try:
        importlib.reload(config_module)
        assert config_module.log_settings.LOG_SQL_ECHO_ENABLED is True
    finally:
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("LOG_SQL_ECHO_ENABLED", raising=False)
        importlib.reload(config_module)


def test_test_database_is_published_on_loopback_only():
    """테스트 MySQL 을 0.0.0.0 에 열면 같은 네트워크의 다른 기기가 접속할 수 있다."""
    compose = (REPO_ROOT / "compose.test.yaml").read_text(encoding="utf-8")
    assert (
        '"127.0.0.1:${MYSQL_TEST_PORT:-3309}:3306"' in compose
    ), "테스트 DB 포트가 loopback 에만 바인딩되지 않았다"
