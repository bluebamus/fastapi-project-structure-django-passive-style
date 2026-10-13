"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

from app.utils.logs.config import LOG_FORMAT, _env, _level, build_dictconfig
from app.utils.logs.redaction import install_record_redaction

_configured = False


def configure_logging(force: bool = False) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent).

    비밀값 가리기(:mod:`app.utils.logs.redaction`)도 여기서 건다 — 핸들러가 아니라
    LogRecord factory 에 걸므로 uvicorn CLI·Celery 처럼 우리가 핸들러를 소유하지 않는
    경로도 같은 규칙을 탄다.
    """
    global _configured
    install_record_redaction()
    if _configured and not force:
        return
    dictConfig(build_dictconfig())
    _configured = True


def get_logger(name: str = "app") -> logging.Logger:
    """설정된 로깅을 공유하는 로거를 반환한다.

    Args:
        name: 로거 이름(모듈명 권장). 헤더의 app 은 소스 경로에서 자동 산출된다.
    """
    configure_logging()
    return logging.getLogger(name)


def setup_uvicorn_logging() -> dict:
    """Uvicorn(log_config)용 dictConfig. 앱 포맷과 동일한 헤더를 사용한다."""
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    access_fmt = (
        "[{asctime} {tzname}] {levelname:5} [app=uvicorn] "
        '{client_addr} - "{request_line}" {status_code}'
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
        },
        "formatters": {
            "default": {
                "()": "app.utils.logs.formatters.TzFormatter",
                "fmt": LOG_FORMAT,
                "use_utc": use_utc,
            },
            "access": {
                "()": "app.utils.logs.formatters.TzFormatter",
                "fmt": access_fmt,
                "use_utc": use_utc,
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "default",
                "filters": ["context"],
            },
            "access": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "formatter": "access",
                "filters": ["context"],
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.error": {"handlers": ["default"], "level": level, "propagate": False},
            "uvicorn.access": {"handlers": ["access"], "level": level, "propagate": False},
        },
    }
