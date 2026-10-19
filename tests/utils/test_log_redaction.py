"""로그 비밀값 가리기 (log-redaction-fixes ADR-001·ADR-002).

각 핸들러 경로를 **실제 구성**(``build_dictconfig()``·``setup_uvicorn_logging()``·uvicorn CLI 의
``LOGGING_CONFIG``·Celery 포매터)으로 적용해 ``logger.exception`` 을 남기고 출력을 본다.
가리기는 ``configure_logging()`` 이 거는 LogRecord factory 가 한다 — 이 파일은 그것을 직접
설치하지 않는다(설치가 빠지면 여기서 떨어져야 한다).
"""

from __future__ import annotations

import copy
import inspect
import io
import logging
from logging.config import dictConfig
from pathlib import Path

import pytest

from app.utils.logs import config as logs_config
from app.utils.logs import setup_uvicorn_logging
from app.utils.logs.redaction import MASK, SecretRedactor, install_record_redaction

DSN = "mysql+asyncmy://u:secret42@h/db"
SECRETS = ("secret42", "xxx-bearer-token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl")


def _raise_chain() -> None:
    """``__cause__``·``__context__`` 를 모두 가진 예외를 던진다."""
    try:
        try:
            raise ValueError(f"connect {DSN} password=secret42")
        except ValueError:
            # 처리 중 다른 예외 → __context__
            raise KeyError(f"Authorization: Bearer {SECRETS[1]}") from None
    except KeyError as exc:
        exc.__suppress_context__ = False
        raise RuntimeError(f"token={SECRETS[2]}") from exc  # __cause__


def _log_exception(logger: logging.Logger) -> int:
    """체인 예외를 ``stack_info=True`` 로 남기고, traceback 에 나와야 할 raise 줄 번호를 돌려준다."""
    try:
        _raise_chain()
    except RuntimeError:
        logger.exception("요청 실패 dsn=%s", DSN, stack_info=True)
    source, start = inspect.getsourcelines(_raise_chain)
    return start + next(i for i, s in enumerate(source) if "raise RuntimeError" in s)


def _assert_redacted(output: str, raise_line: int) -> None:
    for secret in SECRETS:
        assert secret not in output, f"비밀값이 출력에 남았다: {secret}\n{output}"
    assert MASK in output
    # 진단 정보는 남는다 — 예외 타입·체인·파일·줄·stack_info
    for kept in (
        "RuntimeError",
        "KeyError",
        "ValueError",
        "test_log_redaction.py",
        "Stack (most recent call last)",
    ):
        assert kept in output, f"{kept!r} 가 사라졌다\n{output}"
    assert "The above exception was the direct cause" in output
    assert "During handling of the above exception" in output
    assert f"line {raise_line}" in output


def _swap_stream(handler: logging.Handler) -> io.StringIO:
    buf = io.StringIO()
    assert isinstance(handler, logging.StreamHandler)
    handler.setStream(buf)
    return buf


# =============================================================================
# 앱 dictConfig — console · file · error_file
# =============================================================================
#: 사용자 포맷 — 가리기는 포매터가 아니라 LogRecord factory 가 하므로 포맷과 무관해야 한다.
USER_FORMAT = "USR|{levelname}|{name}|{message}"


@pytest.mark.parametrize("user_format", [None, USER_FORMAT], ids=["default", "user-format"])
def test_app_handlers_redact_traceback_message_and_stack(
    restore_logging, monkeypatch, tmp_path: Path, user_format: str | None
):
    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    if user_format:
        for key in ("LOG_CONSOLE_FORMAT", "LOG_FILE_FORMAT"):
            monkeypatch.setattr(logs_config.log_settings, key, user_format, raising=False)
    cfg = logs_config.build_dictconfig()
    assert set(cfg["handlers"]) == {"console", "file", "error_file"}
    dictConfig(cfg)

    root = logging.getLogger()
    console = next(h for h in root.handlers if type(h) is logging.StreamHandler)
    buf = _swap_stream(console)

    line = _log_exception(logging.getLogger("app.redaction"))
    for h in root.handlers:
        h.flush()

    outputs = [buf.getvalue()]
    files = sorted(tmp_path.iterdir())
    assert len(files) == 2  # app · error
    outputs += [f.read_text(encoding="utf-8") for f in files]
    for out in outputs:
        _assert_redacted(out, line)
        # 사용자 포맷이 실제로 적용됐다 — 안 됐으면 이 테스트는 기본 포맷만 다시 본 것이다.
        assert ("USR|ERROR|app.redaction|" in out) == bool(user_format)


def test_third_party_logger_through_root_is_redacted(restore_logging):
    """sqlalchemy 같은 외부 로거도 WARNING 이상은 root 핸들러로 온다(SqlNoiseFilter 통과)."""
    dictConfig(logs_config.build_dictconfig())
    console = next(h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler))
    buf = _swap_stream(console)

    logging.getLogger("sqlalchemy.engine").error("pool 연결 실패 %s", DSN)

    assert "secret42" not in buf.getvalue()
    assert f"u:{MASK}@h/db" in buf.getvalue()


# =============================================================================
# uvicorn — 직접 실행(setup_uvicorn_logging) · CLI(uvicorn 자체 LOGGING_CONFIG)
# =============================================================================
def test_uvicorn_direct_run_handlers_are_redacted(restore_logging):
    dictConfig(setup_uvicorn_logging())
    buf = _swap_stream(logging.getLogger("uvicorn").handlers[0])

    line = _log_exception(logging.getLogger("uvicorn.error"))

    _assert_redacted(buf.getvalue(), line)


def test_uvicorn_cli_handlers_we_do_not_own_are_redacted(restore_logging):
    """``uvicorn main:app`` 은 uvicorn 의 포매터를 쓴다. Starlette 가 500 뒤에 예외를 다시 올려
    uvicorn 이 ``Exception in ASGI application`` traceback 을 이 핸들러로 남긴다."""
    from uvicorn.config import LOGGING_CONFIG

    dictConfig(copy.deepcopy(LOGGING_CONFIG))
    buf = _swap_stream(logging.getLogger("uvicorn").handlers[0])

    line = _log_exception(logging.getLogger("uvicorn.error"))

    _assert_redacted(buf.getvalue(), line)


def test_uvicorn_access_args_stay_a_tuple(restore_logging):
    """AccessFormatter 는 args 를 5-튜플로 푼다 — 가려도 구조를 지켜야 줄이 살아남는다."""
    from uvicorn.config import LOGGING_CONFIG

    dictConfig(copy.deepcopy(LOGGING_CONFIG))
    buf = _swap_stream(logging.getLogger("uvicorn.access").handlers[0])

    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", "/x?password=secret42&page=2", "1.1", 200
    )

    out = buf.getvalue()
    assert "secret42" not in out
    assert f"/x?password={MASK}&page=2" in out
    assert " 200" in out


@pytest.mark.parametrize("path", ["cli", "main.py"])
@pytest.mark.parametrize(
    ("target", "shown", "hidden"),
    [
        ("/x?page=2", "GET /x?page=2 HTTP/1.1", None),
        ("/x?token=abc.def&page=2", f"GET /x?token={MASK}&page=2 HTTP/1.1", "abc.def"),
        (f"/cb?access_token={SECRETS[2]}", f"GET /cb?access_token={MASK} HTTP/1.1", SECRETS[2]),
        # 값이 빈 키·경로 끝의 bearer — 인자 하나만 보면 깨끗한데 템플릿의 " HTTP/1.1" 과 이어 붙이면
        # 규칙에 걸린다. 예전에는 args 를 None 으로 접어 AccessFormatter 가 줄마다 오류를 냈다(F-007).
        ("/x?password=", f"GET {MASK} HTTP/1.1", None),
        ("/x?token=", f"GET {MASK} HTTP/1.1", None),
        ("/auth/bearer", f"GET {MASK} HTTP/1.1", None),
    ],
)
def test_uvicorn_access_line_survives_redaction(
    restore_logging, capsys, path, target, shown, hidden
):
    """접속 줄은 사라지지 않고(logging 오류 없음) 비밀값은 가려진다 — CLI·``python main.py`` 두 경로."""
    from uvicorn.config import LOGGING_CONFIG

    dictConfig(copy.deepcopy(LOGGING_CONFIG) if path == "cli" else setup_uvicorn_logging())
    access = logging.getLogger("uvicorn.access")
    buf = _swap_stream(access.handlers[0])

    access.info('%s - "%s %s HTTP/%s" %d', "1.2.3.4:5", "GET", target, "1.1", 200)

    assert "Logging error" not in capsys.readouterr().err
    out = buf.getvalue()
    assert f'1.2.3.4:5 - "{shown}" 200' in out, out
    if hidden:
        assert hidden not in out


# =============================================================================
# Celery — 워커는 root 핸들러를 자기 포매터로 바꾼다
# =============================================================================
def test_celery_formatter_output_is_redacted(restore_logging):
    from celery.utils.log import ColorFormatter

    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(ColorFormatter("%(levelname)s %(name)s %(message)s", use_color=False))
    logger = logging.getLogger("app.redaction")
    logger.addHandler(handler)

    line = _log_exception(logger)

    _assert_redacted(buf.getvalue(), line)


# =============================================================================
# 규칙
# =============================================================================
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (DSN, f"mysql+asyncmy://u:{MASK}@h/db"),
        ("redis://:p%40ss@localhost:6379/0", f"redis://:{MASK}@localhost:6379/0"),
        ("password=secret42 user=kim", f"password={MASK} user=kim"),
        ("MYSQL_PASSWORD: 'secret42'", f"MYSQL_PASSWORD: '{MASK}'"),
        (
            '{"refresh_token": "abc.def", "token_type": "bearer"}',
            f'{{"refresh_token": "{MASK}", "token_type": "bearer"}}',
        ),
        ("Authorization: Bearer abc.def", f"Authorization: {MASK}"),
        ("header bearer abc.def end", f"header bearer {MASK} end"),
        (f"jwt {SECRETS[2]} end", f"jwt {MASK} end"),
        ("redis://localhost:6379/0", "redis://localhost:6379/0"),
        (
            'File "app/x.py", line 12, in verify_password',
            'File "app/x.py", line 12, in verify_password',
        ),
    ],
)
def test_redaction_rules(text: str, expected: str):
    assert SecretRedactor().redact(text) == expected


def test_redaction_is_idempotent():
    r = SecretRedactor()
    once = r.redact(f"{DSN} password=x Authorization: Bearer y")
    assert r.redact(once) == once


def test_secret_split_between_template_and_argument_is_hidden():
    record = logging.LogRecord("app", logging.INFO, __file__, 1, "password=%s", ("secret42",), None)
    SecretRedactor().redact_record(record)
    assert record.getMessage() == f"password={MASK}"


def test_secret_inside_exception_argument_is_hidden():
    record = logging.LogRecord(
        "app", logging.ERROR, __file__, 1, "실패: %s", (ValueError(DSN),), None
    )
    SecretRedactor().redact_record(record)
    assert "secret42" not in record.getMessage()


def test_install_wraps_the_factory_once():
    original = logging.getLogRecordFactory()
    try:
        install_record_redaction()
        first = logging.getLogRecordFactory()
        install_record_redaction()
        assert logging.getLogRecordFactory() is first
    finally:
        logging.setLogRecordFactory(original)
