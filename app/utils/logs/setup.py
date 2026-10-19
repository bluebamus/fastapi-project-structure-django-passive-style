"""로깅 설정 적용 + 로거 팩토리.

configure_logging() 이 환경별 dictConfig 를 root 로거에 1회 적용하고,
get_logger() 는 그 설정을 공유하는 자식 로거를 돌려준다(핸들러는 root 에만).
"""

from __future__ import annotations

import logging
import sys
from logging.config import dictConfig
from pathlib import Path

from app.utils.logs.config import build_dictconfig
from app.utils.logs.filters import FIXED_HEADERS
from app.utils.logs.redaction import install_record_redaction, redactor
from config import INSTALLED_APPS, log_secret_values, log_settings

_configured = False


def configure_logging(
    force: bool = False, process: str | None = None, logfile: str | None = None
) -> None:
    """환경별 로깅 구성을 root 로거에 적용한다(idempotent).

    비밀값 가리기(:mod:`app.utils.logs.redaction`)도 여기서 건다 — 핸들러가 아니라
    LogRecord factory 에 걸므로 Celery 처럼 우리가 핸들러를 소유하지 않는 경로도 같은 규칙을 탄다.
    ``process``(``web``/``celery``)는 진입점이 정한다 — Celery ``setup_logging`` 수신자가 ``celery`` 로
    부르고, 주지 않으면 :func:`entry_process` 가 진입 명령으로 정한다.
    """
    global _configured
    install_record_redaction()
    if _configured and not force:
        return
    redactor.set_literals(log_secret_values())
    access = logging.getLogger("uvicorn.access")
    # uvicorn --no-access-log 은 handlers=[]·propagate=False 로 끈다 — 다시 켜지 않는다.
    access_off = not access.handlers and not access.propagate
    cfg = build_dictconfig(process or entry_process(), logfile)
    dictConfig(cfg)
    if access_off:
        access.propagate = False
    _configured = True
    if cfg["root"]["handlers"] == ["null"]:
        # 조용히 로그를 잃지 않게 — 로깅이 꺼졌으니 stderr 에 직접 한 줄 남긴다.
        print(
            "[logging] 모든 로그 출력이 꺼져 있습니다 "
            "(LOG_CONSOLE_ENABLED=false, 파일 핸들러 없음 — 파일은 ENV=staging|production + "
            "LOG_FILE_ENABLED=true 일 때만 붙는다)",
            file=sys.stderr,
        )
    unknown = sorted(set(log_settings.app_levels()) - _known_headers())
    if unknown:
        logging.getLogger(__name__).warning(
            "LOG_APP_LEVELS 에 모르는 헤더가 있습니다(오타가 아니면 — 아직 없는 기능 등 — 무시해도 됩니다): %s",
            ", ".join(unknown),
        )


def entry_process() -> str:
    """진입 명령이 ``celery``(워커·beat)면 ``celery``, 아니면 ``web``.

    워커는 ``setup_logging`` 시그널 **전**, ``-A app.celery.app`` 을 import 하는 동안에도 로그를 남긴다.
    그 줄이 웹 ``app.log`` 로 가면 웹과 워커가 한 파일을 회전시킨다 — 그래서 첫 구성부터 나눈다.
    """
    entry = Path(sys.argv[0]) if sys.argv and sys.argv[0] else Path()
    return "celery" if "celery" in (entry.stem.lower(), entry.parent.name.lower()) else "web"


def _known_headers() -> set[str]:
    """``INSTALLED_APPS`` 의 기능명 + 고정 헤더."""
    features = {path.split(".")[2] for path in INSTALLED_APPS if path.startswith("app.features.")}
    return features | FIXED_HEADERS


def get_logger(name: str = "app") -> logging.Logger:
    """설정된 로깅을 공유하는 로거를 반환한다.

    Args:
        name: 로거 이름(모듈명 권장). 헤더의 app 은 소스 경로에서 자동 산출된다.
    """
    configure_logging()
    return logging.getLogger(name)


def setup_uvicorn_logging() -> dict:
    """``python main.py`` 의 ``uvicorn.run(log_config=...)`` 용 — 앱과 **같은** dictConfig 다.

    uvicorn 로거는 자기 핸들러 없이 root 로 전파되므로 서버 줄·접속 줄이 앱 콘솔·파일에 같은 형식으로
    나온다. 접속 줄의 요청 라인(``client - "GET /p HTTP/1.1" 200``)은 uvicorn 이 넘기는 메시지 그대로다.
    """
    return build_dictconfig()
