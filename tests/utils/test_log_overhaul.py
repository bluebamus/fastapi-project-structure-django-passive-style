"""logging-overhaul — 모든 경로 같은 형식(L1)·헤더(L2)·앱별 레벨(L4)·파일 분할(L5)·회전·보관(L6)·비밀값 원문(L7).

경로는 실제 구성으로 재현한다 — 앱 ``build_dictconfig()``, ``python main.py`` 의 ``setup_uvicorn_logging()``,
``uvicorn main:app`` CLI(uvicorn ``LOGGING_CONFIG`` 적용 뒤 앱 import 가 ``configure_logging()``),
Celery 워커(``setup_logging`` 시그널).
"""

from __future__ import annotations

import copy
import io
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from logging.config import dictConfig
from pathlib import Path

import pytest

from app.utils.logs import config as logs_config
from app.utils.logs import setup as logs_setup
from app.utils.logs import setup_uvicorn_logging
from app.utils.logs.filters import _app_from_path
from app.utils.logs.handlers import DailySizeRotatingFileHandler
from app.utils.logs.redaction import MASK, SecretRedactor

#: 프로젝트 기본 형식 한 줄 — [시각 TZ] LEVEL [app=헤더] [module:class:func:line] message
LINE = re.compile(
    r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})? (?:UTC|[A-Z]{2,5})\] "
    r"(?P<level>[A-Z]+) +\[app=(?P<app>[\w-]+)\] \[\w+:[\w-]+:\w+:\d+\] (?P<msg>.*)$"
)
EXT = "/opt/py/lib/python3.14/site-packages/{}/mod.py"


def _set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, env: str = "production", **values):
    monkeypatch.setattr(logs_config.app_settings, "ENV", env, raising=False)
    monkeypatch.setattr(logs_config.log_settings, "LOG_DIR", str(tmp_path), raising=False)
    for key, value in values.items():
        monkeypatch.setattr(logs_config.log_settings, key, value, raising=False)


def _emit(name: str, level: int, msg: str, args: tuple = (), pathname: str | None = None) -> None:
    """외부 라이브러리가 남기는 것처럼 site-packages 경로의 레코드를 흘린다."""
    lg = logging.getLogger(name)
    path = pathname or EXT.format(name.split(".")[0])
    if lg.isEnabledFor(level):
        lg.handle(lg.makeRecord(name, level, path, 1, msg, args, None, "fn"))


def _root_console() -> io.StringIO:
    console = next(h for h in logging.getLogger().handlers if type(h) is logging.StreamHandler)
    buf = io.StringIO()
    console.setStream(buf)
    return buf


def _flush() -> None:
    for h in logging.getLogger().handlers:
        h.flush()


# =============================================================================
# L2 — 헤더: 우리 코드는 경로, 외부 라이브러리는 로거 이름
# =============================================================================
@pytest.mark.parametrize(
    ("logger", "expected"),
    [
        ("celery.worker.strategy", "celery"),
        ("celery", "celery"),
        ("kombu.connection", "celery"),
        ("uvicorn.access", "uvicorn"),
        ("uvicorn.error", "uvicorn"),
        ("sqlalchemy.engine.Engine", "sqlalchemy"),
        ("alembic.runtime.migration", "alembic"),
        ("httpx", "ext"),
        ("celeryx.thing", "ext"),
    ],
)
def test_external_header_comes_from_logger_name(logger, expected):
    assert _app_from_path(EXT.format("pkg"), logger) == expected


def test_our_code_header_ignores_logger_name():
    repo = Path(__file__).resolve().parents[2]
    assert _app_from_path(str(repo / "app" / "features" / "blog" / "x.py"), "uvicorn") == "blog"
    assert _app_from_path(str(repo / "main.py"), "celery") == "app"


# =============================================================================
# L1 — 모든 경로 · 모든 출력처가 같은 형식
# =============================================================================
ACCESS_ARGS = ("1.2.3.4:5", "GET", "/p", "1.1", 200)
ACCESS_MSG = '%s - "%s %s HTTP/%s" %d'


@pytest.mark.parametrize("path", ["main.py", "cli"])
def test_uvicorn_lines_use_project_format(restore_logging, monkeypatch, tmp_path, capsys, path):
    """``python main.py``·``uvicorn main:app`` 모두 접속 줄·서버 줄이 프로젝트 형식이고 요청 줄은 그대로다."""
    _set(monkeypatch, tmp_path, env="development", LOG_FILE_ENABLED=False)
    if path == "cli":
        from uvicorn.config import LOGGING_CONFIG

        dictConfig(copy.deepcopy(LOGGING_CONFIG))  # uvicorn 이 앱 import 전에 거는 구성
        logs_setup.configure_logging(force=True)  # 앱 import(get_logger) 가 거는 구성
    else:
        dictConfig(setup_uvicorn_logging())
    buf = _root_console()

    _emit("uvicorn.access", logging.INFO, ACCESS_MSG, ACCESS_ARGS)
    _emit("uvicorn.error", logging.INFO, "Started server process [%d]", (42,))

    assert "Logging error" not in capsys.readouterr().err
    access, server = buf.getvalue().splitlines()
    m = LINE.match(access)
    assert m and m["app"] == "uvicorn" and m["msg"] == '1.2.3.4:5 - "GET /p HTTP/1.1" 200', access
    m = LINE.match(server)
    assert m and m["app"] == "uvicorn" and m["msg"] == "Started server process [42]", server


def test_uvicorn_cli_no_access_log_is_respected(restore_logging):
    """``--no-access-log`` 은 uvicorn 이 handlers=[]·propagate=False 로 끈다 — 앱 구성이 되살리면 안 된다."""
    from uvicorn.config import LOGGING_CONFIG

    dictConfig(copy.deepcopy(LOGGING_CONFIG))
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False

    logs_setup.configure_logging(force=True)

    assert access.propagate is False and access.handlers == []
    assert logging.getLogger("uvicorn.error").propagate is True


def test_celery_worker_lines_use_project_format(restore_logging, monkeypatch, tmp_path):
    from celery.signals import setup_logging

    import app.celery.app  # noqa: F401 - 수신자 등록

    _set(monkeypatch, tmp_path, env="development", LOG_FILE_ENABLED=False)
    setup_logging.send(sender=None, loglevel=logging.INFO, logfile=None, format="", colorize=False)
    buf = _root_console()

    _emit("celery.worker.consumer", logging.INFO, "Connected to %s", ("redis://h:6379/0",))
    _emit("celery.app.trace", logging.INFO, "Task %s succeeded", ("blog.ping",))
    logging.getLogger("app.celery.task").info("from-task")

    lines = buf.getvalue().splitlines()
    assert [LINE.match(x)["app"] for x in lines] == ["celery", "celery", "app"], lines  # type: ignore[index]


def test_celery_logfile_is_respected_with_project_format(restore_logging, monkeypatch, tmp_path):
    from celery.signals import setup_logging

    import app.celery.app  # noqa: F401 - 수신자 등록

    _set(monkeypatch, tmp_path, env="development", LOG_FILE_ENABLED=False)
    logfile = tmp_path / "worker.log"
    setup_logging.send(
        sender=None, loglevel=logging.INFO, logfile=str(logfile), format="", colorize=False
    )

    _emit("celery.worker", logging.WARNING, "to-logfile")
    _flush()

    (line,) = logfile.read_text(encoding="utf-8").splitlines()
    m = LINE.match(line)
    assert m and m["app"] == "celery" and m["msg"] == "to-logfile", line


# =============================================================================
# L5 — 파일 분할: 프로세스별 + 에러
# =============================================================================
@pytest.mark.parametrize(
    ("process", "files"),
    [("web", ("app.log", "error.log")), ("celery", ("celery.log", "celery-error.log"))],
)
def test_files_are_split_by_process(monkeypatch, tmp_path, process, files):
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True, LOG_RETENTION_DAYS=7)
    cfg = logs_config.build_dictconfig(process=process)

    for handler, name in zip(("file", "error_file"), files, strict=True):
        spec = cfg["handlers"][handler]
        assert spec["()"] == "app.utils.logs.handlers.DailySizeRotatingFileHandler"
        assert Path(spec["filename"]) == tmp_path / name
        assert spec["retention_days"] == 7
        assert spec["max_bytes"] == logs_config.log_settings.LOG_MAX_SIZE_MB * 1024 * 1024
        assert spec["utc"] is True
    assert cfg["handlers"]["error_file"]["level"] == "ERROR"


def test_web_and_worker_write_their_own_files(restore_logging, monkeypatch, tmp_path):
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True)
    for process in ("web", "celery"):
        logs_setup.configure_logging(force=True, process=process)
        logging.getLogger("app.x").error("boom-%s", process)
        _flush()

    def read(name: str) -> str:
        return (tmp_path / name).read_text(encoding="utf-8")

    assert "boom-web" in read("app.log") and "boom-web" in read("error.log")
    assert "boom-celery" in read("celery.log") and "boom-celery" in read("celery-error.log")
    assert "boom-celery" not in read("app.log") + read("error.log")
    for line in read("celery-error.log").splitlines():
        assert LINE.match(line), line


# =============================================================================
# L4 — 헤더별 레벨
# =============================================================================
def test_app_levels_filter_by_header(restore_logging, monkeypatch, tmp_path):
    _set(
        monkeypatch,
        tmp_path,
        env="development",
        LOG_FILE_ENABLED=False,
        LOG_LEVEL="INFO",
        LOG_CONSOLE_LEVEL="DEBUG",
        LOG_APP_LEVELS="blog=DEBUG,sqlalchemy=ERROR",
    )
    logs_setup.configure_logging(force=True)
    assert logging.getLogger().level == logging.DEBUG  # 전체 최솟값까지 내려 필터에 닿게 한다
    buf = _root_console()

    log = logging.getLogger("app.levels")
    log.debug("blog-debug", extra={"appname": "blog"})
    log.debug("core-debug", extra={"appname": "core"})
    log.info("core-info", extra={"appname": "core"})
    _emit("sqlalchemy.pool", logging.WARNING, "sa-warning")
    _emit("sqlalchemy.pool", logging.ERROR, "sa-error")

    out = buf.getvalue()
    assert "blog-debug" in out and "core-info" in out and "sa-error" in out
    assert "core-debug" not in out and "sa-warning" not in out


def test_unknown_header_in_app_levels_warns_once(restore_logging, monkeypatch, tmp_path, capsys):
    _set(
        monkeypatch,
        tmp_path,
        env="development",
        LOG_FILE_ENABLED=False,
        LOG_APP_LEVELS="nosuchapp=DEBUG,blog=INFO,uvicorn=WARNING",
    )
    logs_setup.configure_logging(force=True)

    warned = [line for line in capsys.readouterr().out.splitlines() if "LOG_APP_LEVELS" in line]
    assert len(warned) == 1 and "nosuchapp" in warned[0] and "blog" not in warned[0], warned


# =============================================================================
# L6 — 날짜 + 크기 회전 · 보관일수
# =============================================================================
def _today() -> datetime:
    return datetime.now(UTC)


def _day(days_ago: int) -> str:
    return (_today() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _write(handler: logging.Handler, msg: str) -> None:
    handler.emit(logging.LogRecord("t", logging.INFO, __file__, 1, msg, (), None))


def _handler(tmp_path: Path, **kw) -> DailySizeRotatingFileHandler:
    handler = DailySizeRotatingFileHandler(str(tmp_path / "app.log"), utc=True, **kw)
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def test_midnight_rollover_names_file_by_date(tmp_path):
    handler = _handler(tmp_path)
    try:
        _write(handler, "day-before")
        handler.rolloverAt = int(time.time()) - 1  # 자정이 지났다
        _write(handler, "new-day")
    finally:
        handler.close()

    rolled = tmp_path / f"app.log.{_day(1)}"
    assert rolled.read_text(encoding="utf-8") == "day-before\n"
    assert (tmp_path / "app.log").read_text(encoding="utf-8") == "new-day\n"


def test_size_rollover_splits_within_the_day(tmp_path):
    handler = _handler(tmp_path, max_bytes=20)
    try:
        for i in range(3):
            _write(handler, f"line-{i}-{'x' * 10}")
    finally:
        handler.close()

    today = _day(0)
    assert (tmp_path / f"app.log.{today}.1").read_text(encoding="utf-8").startswith("line-0")
    assert (tmp_path / f"app.log.{today}.2").read_text(encoding="utf-8").startswith("line-1")
    assert (tmp_path / "app.log").read_text(encoding="utf-8").startswith("line-2")


@pytest.mark.parametrize("retention", [3, 0])
def test_retention_deletes_only_older_files(tmp_path, retention):
    keep = [f"app.log.{_day(3)}", f"app.log.{_day(3)}.1", f"app.log.{_day(2)}"]
    old = [f"app.log.{_day(4)}", f"app.log.{_day(40)}.2"]
    others = [f"error.log.{_day(40)}", "app.log.notes", f"app.log.{_day(40)}.bak"]
    for name in keep + old + others:
        (tmp_path / name).write_text("x", encoding="utf-8")

    handler = _handler(tmp_path, retention_days=retention)
    try:
        _write(handler, "a")
        handler.rolloverAt = int(time.time()) - 1
        _write(handler, "b")
    finally:
        handler.close()

    names = {p.name for p in tmp_path.iterdir()}
    assert set(keep + others) <= names
    if retention:
        assert not names & set(old), names & set(old)
    else:
        assert set(old) <= names


# =============================================================================
# L7 — DSN 의 id·비밀번호, 설정 비밀값 원문
# =============================================================================
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mysql+aiomysql://dbuser:pw@h:3306/db", f"mysql+aiomysql://{MASK}:{MASK}@h:3306/db"),
        ("redis://:pw@h:6379/0", f"redis://:{MASK}@h:6379/0"),
        ("redis://h:6379/0", "redis://h:6379/0"),
        # config.REDIS_URL 의 실제 모양 — 사용자명 없음, 비밀번호는 퍼센트 인코딩
        ("redis://:p%40ss%3Aw@h:6379/0", f"redis://:{MASK}@h:6379/0"),
        # 인코딩하지 않은 @·: 가 든 비밀번호 — 마지막 @ 까지가 userinfo 다
        ("redis://:pa@ss:w@h:6379/0", f"redis://:{MASK}@h:6379/0"),
        ("mysql+aiomysql://u:p@ss:w0rd@h/db", f"mysql+aiomysql://{MASK}:{MASK}@h/db"),
        ("mysql://u:p:w@h/db", f"mysql://{MASK}:{MASK}@h/db"),
        # 사용자명만 있는 꼴 — 계정명도 id 다
        ("mysql://dbuser@h/db", f"mysql://{MASK}@h/db"),
        # userinfo 가 아닌 @ 는 건드리지 않는다
        ("http://example.com/a@b mail admin@example.com", "http://example.com/a@b mail admin@example.com"),
    ],
)
def test_dsn_user_and_password_are_masked(text, expected):
    assert SecretRedactor().redact(text) == expected


def test_configured_secret_values_are_masked_anywhere():
    r = SecretRedactor()
    r.set_literals(["Lit3ral-Passw0rd", "dbadmin", "abc", "", "  "])

    assert r.redact("connect with Lit3ral-Passw0rd now") == f"connect with {MASK} now"
    assert r.redact("account dbadmin locked") == f"account {MASK} locked"
    # 4글자 미만은 원문 일치로 가리지 않는다 — user=·username= 과 DSN 에서만
    assert r.redact("abc abcdef xabc") == "abc abcdef xabc"
    assert r.redact("user=abc ok") == f"user={MASK} ok"
    assert r.redact('"username": "abc"') == f'"username": "{MASK}"'
    assert r.redact("user=abcd") == "user=abcd"


SECRET_PW = "Lit3ral-Passw0rd-9"
SECRET_USER = "svc_dbuser"


@pytest.mark.parametrize("path", ["app", "uvicorn-cli", "celery"])
def test_secret_values_never_reach_any_output(restore_logging, monkeypatch, tmp_path, path):
    from config import db_settings

    monkeypatch.setattr(db_settings, "MYSQL_PASSWORD", SECRET_PW)
    monkeypatch.setattr(db_settings, "MYSQL_USER", SECRET_USER)
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True)
    if path == "uvicorn-cli":
        from uvicorn.config import LOGGING_CONFIG

        dictConfig(copy.deepcopy(LOGGING_CONFIG))
        logs_setup.configure_logging(force=True)
    elif path == "celery":
        from celery.signals import setup_logging

        import app.celery.app  # noqa: F401

        setup_logging.send(
            sender=None, loglevel=logging.INFO, logfile=None, format="", colorize=False
        )
    else:
        logs_setup.configure_logging(force=True)
    buf = _root_console()

    name = {"app": "app.secret", "uvicorn-cli": "uvicorn.error", "celery": "celery.worker"}[path]
    try:
        try:
            raise ValueError(f"login as {SECRET_USER} with {SECRET_PW}")
        except ValueError as inner:
            raise RuntimeError("wrapped") from inner
    except RuntimeError:
        logging.getLogger(name).exception("failed for %s", SECRET_USER, stack_info=True)
    _flush()

    outputs = [buf.getvalue()] + [p.read_text(encoding="utf-8") for p in tmp_path.glob("*.log")]
    assert len(outputs) == 3
    for out in outputs:
        assert "ValueError" in out and MASK in out
        assert SECRET_PW not in out and SECRET_USER not in out, out


@pytest.mark.parametrize(
    ("argv0", "files"),
    [
        ("C:/venv/Scripts/celery", ("celery.log", "celery-error.log")),
        ("/venv/bin/celery.exe", ("celery.log", "celery-error.log")),
        ("/venv/lib/site-packages/celery/__main__.py", ("celery.log", "celery-error.log")),
        ("/venv/bin/uvicorn", ("app.log", "error.log")),
        ("main.py", ("app.log", "error.log")),
    ],
)
def test_import_time_lines_of_worker_go_to_worker_files(monkeypatch, tmp_path, argv0, files):
    """워커는 ``setup_logging`` 시그널 전(모듈 import 중)에도 로그를 남긴다 — 그 줄이 웹 app.log 로 가면
    웹과 워커가 같은 파일을 회전시킨다. 진입 명령(``celery``)으로 기본 프로세스 종류를 정한다."""
    monkeypatch.setattr("sys.argv", [argv0, "-A", "app.celery.app", "worker"])
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True)
    captured = []
    monkeypatch.setattr(logs_setup, "dictConfig", captured.append)

    logs_setup.configure_logging(force=True)

    names = tuple(Path(captured[0]["handlers"][h]["filename"]).name for h in ("file", "error_file"))
    assert names == files


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["/venv/bin/celery", "-A", "app.celery.app", "beat", "-l", "info"], "beat"),
        (["/venv/bin/celery", "-A", "app.celery.app", "worker"], "celery"),
        (["/venv/bin/pytest", "tests"], "web"),
    ],
)
def test_entry_process(monkeypatch, argv, expected):
    """beat 는 워커와 다른 프로세스다 — 같은 celery.log 를 둘이 회전시키지 않게 따로 둔다."""
    monkeypatch.setattr("sys.argv", argv)
    assert logs_setup.entry_process() == expected
    assert logs_config.LOG_FILES["beat"] == ("celery-beat.log", "celery-beat-error.log")


def test_celery_receiver_in_beat_uses_beat_files(restore_logging, monkeypatch, tmp_path):
    from celery.signals import setup_logging

    import app.celery.app  # noqa: F401 - 수신자 등록

    monkeypatch.setattr("sys.argv", ["/venv/bin/celery", "-A", "app.celery.app", "beat"])
    _set(monkeypatch, tmp_path, LOG_FILE_ENABLED=True)
    setup_logging.send(sender=None, loglevel=logging.INFO, logfile=None, format="", colorize=False)

    logging.getLogger("celery.beat").error("beat-boom")
    _flush()
    assert "beat-boom" in (tmp_path / "celery-beat-error.log").read_text(encoding="utf-8")
    assert not (tmp_path / "celery.log").exists()
