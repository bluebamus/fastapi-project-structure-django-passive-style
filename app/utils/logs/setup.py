"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).
"""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig

from app.utils.logs.config import (
    _env,
    _level,
    build_dictconfig,
    console_enabled,
    formatter_spec,
)
from app.utils.logs.redaction import install_record_redaction
from config import log_settings

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
    cfg = build_dictconfig()
    dictConfig(cfg)
    _configured = True
    if cfg["root"]["handlers"] == ["null"]:
        # 조용히 로그를 잃지 않게 — 로깅이 꺼졌으니 stderr 에 직접 한 줄 남긴다.
        print(
            "[logging] 모든 로그 출력이 꺼져 있습니다 "
            "(LOG_CONSOLE_ENABLED=false, 파일 핸들러 없음 — 파일은 ENV=staging|production + "
            "LOG_FILE_ENABLED=true 일 때만 붙는다)",
            file=sys.stderr,
        )


def get_logger(name: str = "app") -> logging.Logger:
    """설정된 로깅을 공유하는 로거를 반환한다.

    Args:
        name: 로거 이름(모듈명 권장). 헤더의 app 은 소스 경로에서 자동 산출된다.
    """
    configure_logging()
    return logging.getLogger(name)


def setup_uvicorn_logging() -> dict:
    """Uvicorn(log_config)용 dictConfig. 앱 포맷과 동일한 헤더를 사용한다.

    ``default`` 는 ``LOG_CONSOLE_FORMAT``, 둘 다 ``LOG_DATE_FORMAT`` 을 따른다. access 줄은
    요청 라인 전용 형식이라 고정이다. ``LOG_CONSOLE_ENABLED=false`` 면 콘솔 핸들러를 만들지
    않고 root(파일 핸들러가 있으면 그쪽)로 전파한다.
    """
    env = _env()
    level = _level()
    use_utc = env in ("production", "staging")
    # {client_addr}·{request_line}·{status_code} 는 uvicorn AccessFormatter 만 채운다 — TzFormatter 에서
    # 쓰면 줄마다 logging 오류. uvicorn 이 넘기는 메시지가 이미 `client - "METHOD path HTTP/v" status` 다.
    access_fmt = "[{asctime} {tzname}] {levelname:5} [app=uvicorn] {message}"
    console = console_enabled()
    handlers: dict = {}
    if console:
        handlers = {
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
        }

    def _logger(handler: str) -> dict:
        return {
            "handlers": [handler] if console else [],
            "level": level,
            "propagate": not console,
        }

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "context": {"()": "app.utils.logs.filters.ContextFilter"},
        },
        "formatters": {
            "default": formatter_spec(log_settings.LOG_CONSOLE_FORMAT, use_utc),
            "access": formatter_spec(access_fmt, use_utc),
        },
        "handlers": handlers,
        "loggers": {
            "uvicorn": _logger("default"),
            "uvicorn.error": _logger("default"),
            "uvicorn.access": _logger("access"),
        },
    }
