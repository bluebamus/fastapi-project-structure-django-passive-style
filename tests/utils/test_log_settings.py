"""로그 설정(LOG_CONSOLE_FORMAT·LOG_FILE_FORMAT·LOG_DATE_FORMAT·LOG_CONSOLE_ENABLED) 결선 (config-cleanup-2).

각 값이 실제 출력 줄과 핸들러 구성에 닿는지 본다 — 앱 dictConfig·uvicorn 직접 실행·Celery 워커.
"""

from __future__ import annotations

import io
import logging
from logging.config import dictConfig
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.utils.logs import config as logs_config
from app.utils.logs import setup as logs_setup
from app.utils.logs import setup_uvicorn_logging
from app.utils.logs.formatters import TzFormatter
from config import LogSettings

#: 변경 전 ``app/utils/logs/config.py`` 에 하드코딩돼 있던 형식 — 기본값이 이것과 같아야 출력이 그대로다.
PREVIOUS_FORMAT = (
    "[{asctime} {tzname}] {levelname:5} [app={appname}] "
    "[{module}:{classname}:{funcName}:{lineno}] {message}"
)
PREVIOUS_DATEFMT = "%Y-%m-%d %H:%M:%S"

# 2026-01-02 03:04:05.678 UTC
CREATED = 1767323045.678


def _record(msg: str = "hello") -> logging.LogRecord:
    rec = logging.LogRecord("app.fmt", logging.INFO, __file__, 7, msg, (), None, "fn")
    rec.created = CREATED
    rec.msecs = 678.0
    return rec


def _formatter(spec: dict) -> TzFormatter:
    """dictConfig 의 formatter 항목을 실제 객체로 만든다."""
    return TzFormatter(**{k: v for k, v in spec.items() if k != "()"})


def _set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: str = "production", **values):
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in values.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)


def _console_handlers(handlers: dict) -> list[str]:
    return [name for name, h in handlers.items() if h.get("class") == "logging.StreamHandler"]


# =============================================================================
# 기본값 = 변경 전 출력
# =============================================================================
def test_format_defaults_equal_previous_hardcoded_values(monkeypatch):
    for key in ("LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT", "LOG_DATE_FORMAT"):
        monkeypatch.delenv(key, raising=False)
    settings = LogSettings(_env_file=None)  # type: ignore[call-arg]

    assert settings.LOG_CONSOLE_FORMAT == PREVIOUS_FORMAT
    assert settings.LOG_FILE_FORMAT == PREVIOUS_FORMAT
    assert settings.LOG_DATE_FORMAT == PREVIOUS_DATEFMT


@pytest.mark.parametrize("env", ["development", "production"])
def test_default_output_line_is_unchanged(monkeypatch, tmp_path, env):
    """기본값 구성의 출력 줄 = 변경 전 하드코딩 포매터의 출력 줄(개발 밀리초 포함)."""
    _set(monkeypatch, tmp_path, env=env)
    for key, value in (
        ("LOG_CONSOLE_FORMAT", PREVIOUS_FORMAT),
        ("LOG_FILE_FORMAT", PREVIOUS_FORMAT),
        ("LOG_DATE_FORMAT", PREVIOUS_DATEFMT),
    ):
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)
    cfg = logs_config.build_dictconfig()

    use_utc = env == "production"
    previous = TzFormatter(PREVIOUS_FORMAT, use_utc=use_utc, with_ms=env == "development")
    assert _formatter(cfg["formatters"]["app"]).format(_record()) == previous.format(_record())
    if env == "development":
        assert ".678" in previous.format(_record())


# =============================================================================
# 포맷·날짜 형식이 출력 줄을 정한다
# =============================================================================
def test_console_format_and_date_format_shape_app_output(monkeypatch, tmp_path):
    _set(
        monkeypatch,
        tmp_path,
        LOG_FILE_ENABLED=False,
        LOG_CONSOLE_FORMAT="C|{asctime}|{levelname}|{message}",
        LOG_DATE_FORMAT="%d/%m/%Y %H.%M",
    )
    cfg = logs_config.build_dictconfig()

    console = cfg["handlers"]["console"]
    line = _formatter(cfg["formatters"][console["formatter"]]).format(_record())
    assert line == "C|02/01/2026 03.04|INFO|hello"


def test_file_format_is_written_to_file(restore_logging, monkeypatch, tmp_path):
    _set(
        monkeypatch,
        tmp_path,
        LOG_FILE_ENABLED=True,
        LOG_FILE_FORMAT="F|{asctime}|{levelname}|{message}",
        LOG_DATE_FORMAT="%Y%m%d",
    )
    dictConfig(logs_config.build_dictconfig())

    logging.getLogger("app.fmt").warning("to-file")
    for h in logging.getLogger().handlers:
        h.flush()

    app_log = tmp_path / "app.log"
    lines = app_log.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("|WARNING|to-file") and line.startswith("F|20") for line in lines)


def test_uvicorn_direct_run_follows_console_format_and_date(monkeypatch, tmp_path):
    _set(
        monkeypatch,
        tmp_path,
        LOG_CONSOLE_FORMAT="U|{asctime}|{message}",
        LOG_DATE_FORMAT="%Y",
    )
    cfg = setup_uvicorn_logging()

    assert _formatter(cfg["formatters"]["app"]).format(_record()) == "U|2026|hello"
    # 접속 줄 전용 포매터는 없다 — uvicorn 로거는 root(앱 콘솔·파일)로 전파된다.
    assert set(cfg["formatters"]) == {"app", "file"}
    assert all(f["datefmt"] == "%Y" for f in cfg["formatters"].values())


def test_uvicorn_direct_run_access_line_renders(restore_logging, monkeypatch, tmp_path, capsys):
    """``python main.py`` 의 접속 로그 한 줄 — uvicorn 이 남기는 그대로의 레코드를 흘린다.

    ``{client_addr}``·``{request_line}``·``{status_code}`` 는 uvicorn ``AccessFormatter`` 만 채운다.
    ``TzFormatter`` 가 그 필드를 쓰면 줄마다 logging 오류(stderr)가 나고 접속 로그가 사라진다.
    """
    _set(monkeypatch, tmp_path, env="production", LOG_DATE_FORMAT="%Y/%m/%d")
    dictConfig(setup_uvicorn_logging())
    access = logging.getLogger("uvicorn.access")
    buf = io.StringIO()
    next(h for h in logging.getLogger().handlers if type(h) is logging.StreamHandler).setStream(buf)

    # uvicorn.protocols.http 의 호출과 같은 모양(5-튜플 args, uvicorn 패키지 경로)
    args = ("1.2.3.4:5", "GET", "/x?password=secret42", "1.1", 200)
    path = "/py/site-packages/uvicorn/protocols/http/h11_impl.py"
    access.handle(
        access.makeRecord(access.name, logging.INFO, path, 1, '%s - "%s %s HTTP/%s" %d', args, None)
    )

    assert capsys.readouterr().err == "", "접속 로그 포맷 오류가 stderr 로 나갔다"
    line = buf.getvalue().strip()
    assert "INFO  [app=uvicorn] [h11_impl:-:" in line, line  # 앱과 같은 형식 — 헤더는 로거 이름에서
    assert line.endswith('] 1.2.3.4:5 - "GET /x?password=*** HTTP/1.1" 200'), line
    assert line.startswith("[20") and " UTC] " in line and line[5] == "/"  # LOG_DATE_FORMAT·UTC


def test_celery_worker_uses_app_logging(restore_logging, monkeypatch, tmp_path):
    """Celery 는 ``setup_logging`` 수신자가 있으면 root 를 가로채지 않는다 — 우리 구성을 쓴다."""
    from celery.signals import setup_logging

    import app.celery.app  # noqa: F401 - 수신자 등록

    _set(
        monkeypatch,
        tmp_path,
        LOG_FILE_ENABLED=False,
        LOG_CONSOLE_FORMAT="W|{levelname}|{message}",
    )
    receivers = setup_logging.send(
        sender=None, loglevel=logging.WARNING, logfile=None, format="", colorize=False
    )
    assert receivers, "setup_logging 수신자가 없으면 Celery 가 root 핸들러를 자기 것으로 바꾼다"

    root = logging.getLogger()
    assert root.level == logging.WARNING  # --loglevel 은 그대로 따른다
    console = next(h for h in root.handlers if type(h) is logging.StreamHandler)
    buf = io.StringIO()
    console.setStream(buf)
    logging.getLogger("celery.task").warning("from-worker")
    assert buf.getvalue().splitlines()[-1] == "W|WARNING|from-worker"


# =============================================================================
# LOG_CONSOLE_ENABLED
# =============================================================================
def test_console_disabled_removes_only_console_handlers(monkeypatch, tmp_path):
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True, LOG_CONSOLE_ENABLED=False)
    cfg = logs_config.build_dictconfig()

    assert _console_handlers(cfg["handlers"]) == []
    assert cfg["root"]["handlers"] == ["file", "error_file"]

    uv = setup_uvicorn_logging()
    assert _console_handlers(uv["handlers"]) == []
    for name, spec in uv["loggers"].items():
        # 자기 핸들러가 없으니 root(파일)로 보낸다 — 막으면 lastResort 가 stderr 로 찍는다.
        assert spec["handlers"] == [] and spec["propagate"] is True, name


def test_console_enabled_keeps_console_handlers(monkeypatch, tmp_path):
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=False, LOG_CONSOLE_ENABLED=True)
    assert _console_handlers(logs_config.build_dictconfig()["handlers"]) == ["console"]
    assert _console_handlers(setup_uvicorn_logging()["handlers"]) == ["console"]


def test_all_outputs_off_warns_once_on_stderr(restore_logging, monkeypatch, tmp_path, capsys):
    _set(monkeypatch, tmp_path, env="development", LOG_CONSOLE_ENABLED=False, LOG_FILE_ENABLED=True)
    logs_setup.configure_logging(force=True)

    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and "LOG_CONSOLE_ENABLED" in err[0]
    # 핸들러가 하나도 없으면 logging.lastResort 가 WARNING 이상을 stderr 로 찍는다 — 막혀 있어야 한다.
    logging.getLogger("app.fmt").error("silent")
    assert capsys.readouterr().err == ""


def test_console_off_with_file_does_not_warn(restore_logging, monkeypatch, tmp_path, capsys):
    _set(monkeypatch, tmp_path, LOG_CONSOLE_ENABLED=False, LOG_FILE_ENABLED=True)
    logs_setup.configure_logging(force=True)
    assert capsys.readouterr().err == ""


# =============================================================================
# 설정 검증
# =============================================================================
@pytest.mark.parametrize("key", ["LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT"])
@pytest.mark.parametrize("bad", ["{foo} {message}", "{message", "no fields"])
def test_invalid_format_is_rejected_at_load(monkeypatch, key, bad):
    monkeypatch.setenv(key, bad)
    with pytest.raises(ValidationError, match=key):
        LogSettings(_env_file=None)  # type: ignore[call-arg]


def test_empty_date_format_is_rejected(monkeypatch):
    monkeypatch.setenv("LOG_DATE_FORMAT", " ")
    with pytest.raises(ValidationError, match="LOG_DATE_FORMAT"):
        LogSettings(_env_file=None)  # type: ignore[call-arg]


def test_valid_custom_format_loads(monkeypatch):
    monkeypatch.setenv(
        "LOG_CONSOLE_FORMAT",
        "{asctime} {levelname} {appname} {module} {classname} {funcName} {message}",
    )
    assert LogSettings(_env_file=None).LOG_CONSOLE_FORMAT.startswith("{asctime}")  # type: ignore[call-arg]


# =============================================================================
# logging-overhaul — 필수 필드(L3) · 앱별 레벨(L4) · 보관일수(L6)
# =============================================================================
@pytest.mark.parametrize("key", ["LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT"])
def test_format_without_required_fields_is_rejected(monkeypatch, key):
    monkeypatch.setenv(key, "{asctime} {levelname} {message}")
    with pytest.raises(ValidationError) as exc:
        LogSettings(_env_file=None)  # type: ignore[call-arg]
    text = str(exc.value)
    for field in ("appname", "module", "classname", "funcName"):
        assert field in text


def test_default_formats_have_every_required_field():
    from config import REQUIRED_LOG_FIELDS

    for field in REQUIRED_LOG_FIELDS:
        assert "{" + field in PREVIOUS_FORMAT


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", {}),
        (
            "blog=DEBUG, celery=info ,sqlalchemy=WARNING",
            {"blog": 10, "celery": 20, "sqlalchemy": 30},
        ),
    ],
)
def test_app_levels_parse(monkeypatch, raw, expected):
    monkeypatch.setenv("LOG_APP_LEVELS", raw)
    assert LogSettings(_env_file=None).app_levels() == expected  # type: ignore[call-arg]


@pytest.mark.parametrize("raw", ["blog=LOUD", "blog", "=DEBUG", "blog=DEBUG,blog=INFO"])
def test_invalid_app_levels_are_rejected(monkeypatch, raw):
    monkeypatch.setenv("LOG_APP_LEVELS", raw)
    with pytest.raises(ValidationError, match="LOG_APP_LEVELS"):
        LogSettings(_env_file=None)  # type: ignore[call-arg]


def test_retention_days_default_zero_and_negative(monkeypatch):
    monkeypatch.delenv("LOG_RETENTION_DAYS", raising=False)
    assert LogSettings(_env_file=None).LOG_RETENTION_DAYS == 30  # type: ignore[call-arg]
    monkeypatch.setenv("LOG_RETENTION_DAYS", "0")
    assert LogSettings(_env_file=None).LOG_RETENTION_DAYS == 0  # type: ignore[call-arg]
    monkeypatch.setenv("LOG_RETENTION_DAYS", "-1")
    with pytest.raises(ValidationError, match="LOG_RETENTION_DAYS"):
        LogSettings(_env_file=None)  # type: ignore[call-arg]
