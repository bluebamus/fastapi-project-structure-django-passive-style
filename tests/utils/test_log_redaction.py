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
from collections.abc import Iterator
from logging.config import dictConfig
from pathlib import Path

import pytest

from app.utils.logs import config as logs_config
from app.utils.logs import configure_logging, setup_uvicorn_logging
from app.utils.logs.redaction import MASK, SecretRedactor, install_record_redaction

DSN = "mysql+asyncmy://u:secret42@h/db"
SECRETS = ("secret42", "xxx-bearer-token", "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl")

_WATCHED = ("", "uvicorn", "uvicorn.error", "uvicorn.access", "app.redaction", "sqlalchemy.engine")


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """dictConfig 는 전역이다 — 이 테스트가 바꾼 로거 상태를 되돌린다."""
    saved = {
        name: (list(lg.handlers), lg.level, lg.propagate, lg.disabled)
        for name in _WATCHED
        for lg in [logging.getLogger(name)]
    }
    configure_logging()
    yield
    for name, (handlers, level, propagate, disabled) in saved.items():
        lg = logging.getLogger(name)
        for h in lg.handlers:
            if h not in handlers:
                h.close()
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled


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
def test_app_handlers_redact_traceback_message_and_stack(
    restore_logging, monkeypatch, tmp_path: Path
):
    monkeypatch.setattr(logs_config.app_settings, "ENV", "production", raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_FILE_ENABLED", True, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    cfg = logs_config.build_dictconfig()
    assert set(cfg["handlers"]) == {"console", "file", "error_file"}
    dictConfig(cfg)

    root = logging.getLogger()
    console = next(h for h in root.handlers if type(h) is logging.StreamHandler)
    buf = _swap_stream(console)

    line = _log_exception(logging.getLogger("app.redaction"))
    for h in root.handlers:
        h.flush()

    _assert_redacted(buf.getvalue(), line)
    files = sorted(tmp_path.iterdir())
    assert len(files) == 2  # app · error
    for f in files:
        _assert_redacted(f.read_text(encoding="utf-8"), line)


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
