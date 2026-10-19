"""환경별 로깅 dictConfig 빌더 — 설정 단일 지점.

ENV(development/test/staging/production)에 따라 레벨·핸들러·타임존을 다르게 구성한다.
- development (uv run fastapi dev): 콘솔, DEBUG, 밀리초, 로컬 TZ(KST)
- test: 콘솔, 간결, 파일 off, 로컬 TZ
- staging/production: 콘솔 + 회전 파일 + 에러 파일, INFO, UTC

Django 와 같은 점 / 다른 점 (ADR-019 — 이 설계를 유지하기로 확정했다):
    같다   — 설정이 한 곳에 모인다. Django 의 ``settings.LOGGING`` 자리를
             ``build_dictconfig()`` 가 맡고, ``configure_logging()`` 이 1회 적용한다.
    다르다 — **앱별 로거를 등록하지 않는다.** 아래 dict 에 ``loggers`` 키가 없고
             핸들러는 **root 에만** 붙는다. ``get_logger(name)`` 이 돌려주는 것은
             NOTSET·핸들러 0·propagate=True 인 자식 로거이며, 로그 헤더의 ``app=`` 은
             로거 이름이 아니라 **소스 파일 경로**에서 산출된다
             (``filters.ContextFilter`` → ``_app_from_path``).

왜 이렇게 하나:
    새 기능을 추가할 때 로깅 설정에 **손댈 곳이 0** 이다. Django 라면 ``LOGGING["loggers"]``
    에 한 줄을 더해야 하고, 그 한 줄을 빠뜨리면 조용히 기본값으로 흘러간다. 경로 기반
    판별은 등록 누락이라는 실패 모드 자체를 없앤다. 로거 이름을 잘못 줘도(복사·붙여넣기)
    ``app=`` 라벨은 항상 맞다.

이 선택이 포기한 것 (수용된 잔여 위험 — 결함으로 재보고하지 말 것):
    · **앱별 로그 레벨을 따로 줄 수 없다.** 레벨은 root 하나뿐이고
      ``LogSettings`` 에도 전역 레벨(``LOG_LEVEL``·``LOG_CONSOLE_LEVEL``·``LOG_FILE_LEVEL``)만 있다.
    · **서드파티 로거(sqlalchemy·aiomysql 등)를 개별 제어할 수 없다.** 아래 dict 에
      해당 항목이 없어 전부 root 레벨을 따른다.
    둘 중 하나가 실제로 필요해지면 그때 ``loggers`` 키를 추가한다 —
    그 시점에 charter 비목표를 먼저 개정한다.
"""

from __future__ import annotations

import logging

from config import DEFAULT_LOG_FORMAT, app_settings, log_settings

# 확정 포맷 (#3): [시간 TZ] LEVEL [app=..] [module:class:func:line] message
# 실제로 쓰는 형식은 LOG_CONSOLE_FORMAT·LOG_FILE_FORMAT 이고, 이 값은 그 기본값이다.
LOG_FORMAT = DEFAULT_LOG_FORMAT


def _env() -> str:
    return getattr(app_settings, "ENV", "development")


def _level() -> str:
    return log_settings.get_effective_log_level(app_settings.DEBUG)


def console_enabled() -> bool:
    """콘솔 핸들러를 붙일지 — 앱·uvicorn(``setup_uvicorn_logging``)·Celery 워커가 모두 여기를 본다."""
    return log_settings.LOG_CONSOLE_ENABLED


def formatter_spec(fmt: str, use_utc: bool, with_ms: bool = False) -> dict:
    """``TzFormatter`` dictConfig 항목 — 날짜 형식은 ``LOG_DATE_FORMAT`` 하나를 함께 쓴다."""
    return {
        "()": "app.utils.logs.formatters.TzFormatter",
        "fmt": fmt,
        "datefmt": log_settings.LOG_DATE_FORMAT,
        "use_utc": use_utc,
        "with_ms": with_ms,
    }


#: 프로세스 종류 → (일반 파일, 에러 파일). 웹과 워커가 같은 파일을 회전시키지 않게 나눈다(ADR-003).
LOG_FILES = {
    "web": ("app.log", "error.log"),
    "celery": ("celery.log", "celery-error.log"),
}

#: uvicorn 로거는 자기 핸들러 없이 root 로 보낸다 — ``python main.py``·``uvicorn main:app`` CLI 모두
#: 앱 핸들러(콘솔·파일)·포맷·헤더·레벨을 그대로 탄다(ADR-001). 앱별 로거 등록이 아니다.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def build_dictconfig(process: str = "web", logfile: str | None = None) -> dict:
    """앱·uvicorn·Celery 워커가 함께 쓰는 dictConfig.

    Args:
        process: ``web``(기본) 또는 ``celery`` — 파일 이름을 정한다. 정하는 곳은 진입점
            (``configure_logging`` 기본값 = 웹, Celery ``setup_logging`` 수신자 = celery)이다.
        logfile: Celery ``--logfile`` — 주면 그 파일에도 같은 형식으로 쓴다.
    """
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    with_ms = env == "development"
    app_levels = log_settings.app_levels()
    filters = ["sql_noise", "context", "app_levels"]

    handlers: dict = {}
    root_handlers: list[str] = []
    if console_enabled():
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "app",
            "filters": filters,
            "level": log_settings.get_effective_console_level(app_settings.DEBUG),
        }
        root_handlers.append("console")

    if env in ("production", "staging") and log_settings.LOG_FILE_ENABLED:
        log_dir = log_settings.get_log_dir()
        for name, filename, file_level in zip(
            ("file", "error_file"),
            LOG_FILES[process],
            (log_settings.LOG_FILE_LEVEL, "ERROR"),
            strict=True,
        ):
            handlers[name] = {
                "()": "app.utils.logs.handlers.DailySizeRotatingFileHandler",
                "filename": str(log_dir / filename),
                "max_bytes": log_settings.LOG_MAX_SIZE_MB * 1024 * 1024,
                "retention_days": log_settings.LOG_RETENTION_DAYS,
                # 파일은 staging/production 에서만 붙고 그 시각은 UTC 다 — 자정도 UTC 로 맞춘다(ADR-004).
                "utc": use_utc,
                "formatter": "file",
                "filters": filters,
                "level": file_level,
            }
            root_handlers.append(name)

    if logfile:
        handlers["logfile"] = {
            "class": "logging.FileHandler",
            "filename": logfile,
            "encoding": "utf-8",
            "formatter": "file",
            "filters": filters,
        }
        root_handlers.append("logfile")

    if not root_handlers:
        # 출력이 모두 꺼졌다. 핸들러 0개면 logging.lastResort 가 WARNING 이상을 stderr 로
        # 찍는다 — 끈 것은 끈 것이다. 경고 한 줄은 configure_logging() 이 남긴다.
        handlers["null"] = {"class": "logging.NullHandler"}
        root_handlers.append("null")

    level_no = logging.getLevelName(level.upper())
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
            # SQL 본문·바인딩 파라미터 유출 차단. **모든** 핸들러에 붙는다 —
            # 하나라도 빠지면 그 경로로 그대로 샌다 (C-5).
            "sql_noise": {
                "()": "app.utils.logs.filters.SqlNoiseFilter",
                "allow_sql_echo": log_settings.LOG_SQL_ECHO_ENABLED,
            },
            # 헤더별 최소 레벨(LOG_APP_LEVELS). context 뒤에 있어야 appname 이 채워져 있다.
            "app_levels": {
                "()": "app.utils.logs.filters.AppLevelFilter",
                "levels": app_levels,
                "default": level_no,
            },
        },
        "formatters": {
            "app": formatter_spec(log_settings.LOG_CONSOLE_FORMAT, use_utc, with_ms),
            "file": formatter_spec(log_settings.LOG_FILE_FORMAT, use_utc, with_ms),
        },
        "handlers": handlers,
        "loggers": {
            name: {"handlers": [], "propagate": True, "level": "NOTSET"} for name in UVICORN_LOGGERS
        },
        # 레코드가 필터까지 오도록 root 는 전체 최솟값 — 실제 컷은 app_levels 필터가 한다.
        "root": {"handlers": root_handlers, "level": min([level_no, *app_levels.values()])},
    }
