"""중앙 Celery 앱 (service-hardening ADR-012).

태스크는 각 기능의 ``tasks`` module(``app/features/<앱>/tasks.py``, 선택)에 둔다. 워커의
``include`` 는 ``config.INSTALLED_APPS`` 로 채운 App Registry 가 만든다 — 이 패키지는
어떤 기능도 직접 import 하지 않는다(C-14). ``INSTALLED_APPS`` 에서 앱을 빼면 그 앱의
태스크와 모델도 워커에서 빠진다(Django ``autodiscover_tasks`` 와 같은 방식).
"""

import logging
from collections.abc import Sequence
from typing import Any

from celery import Celery
from celery.signals import setup_logging

from app.core.apps import Apps
from app.utils.logs import configure_logging
from app.utils.logs.setup import entry_process
from config import INSTALLED_APPS, redis_settings, timezone_settings


@setup_logging.connect
def use_app_logging(
    loglevel: int | str | None = None, logfile: str | None = None, **_: Any
) -> None:
    """워커·beat 도 앱 로깅 구성(``build_dictconfig``)을 쓴다 — Celery 쪽 로깅 진입점.

    수신자가 있으면 Celery 는 root 핸들러를 자기 포매터로 갈아끼우지 않는다 — 그래서 콘솔 스위치·
    포맷·헤더·앱별 레벨이 워커에도 그대로 적용되고, 파일은 ``celery.log``·``celery-error.log``(beat 는
    ``celery-beat.log``·``celery-beat-error.log``)로 간다.
    ``--loglevel`` 은 root 레벨로 따르고, ``--logfile`` 을 주면 그 파일에도 같은 형식으로 쓴다.
    """
    configure_logging(force=True, process=entry_process(default="celery"), logfile=logfile)
    if loglevel:
        logging.getLogger().setLevel(loglevel)


def discover_task_modules(installed_apps: Sequence[str]) -> list[str]:
    """``installed_apps`` 로 새 registry 를 채우고 태스크 module 경로를 돌려준다.

    모델 단계까지 채우므로(``run_ready=False``) 워커에서도 모든 설치 앱의 mapper 가
    등록된다 — 관계를 문자열로 참조하는 모델이 첫 쿼리에서 실패하지 않는다.
    ``ready()`` 는 돌리지 않는다: 접속 로그 sink 결선 같은 API 프로세스 전용 부수효과다.
    API 의 전역 registry 와 상태를 섞지 않도록 독립 인스턴스를 쓴다.
    """
    registry = Apps()
    registry.populate(installed_apps, run_ready=False)
    return registry.task_modules()


celery_app = Celery(
    "project",
    broker=redis_settings.REDIS_URL,
    backend=redis_settings.REDIS_URL,
    include=discover_task_modules(INSTALLED_APPS),
)
# worker 프로세스 종료 훅을 등록한다. import 만으로 signal 이 연결되므로 여기서
# 한 번 끌어온다 — worker 는 이 모듈을 반드시 로드하기 때문이다. 이걸 빠뜨리면
# 루프에 묶인 DB 커넥션이 종료 시 정리되지 않고 서버 쪽에 남는다.
from app.celery import lifecycle  # noqa: E402,F401 - signal 등록 부수효과

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # 내부 시각(ETA·만료·결과 메타데이터)은 UTC 로 다룬다 — DB 저장과 같은 기준이다
    # (service-hardening ADR-010). ``timezone`` 은 crontab 같은 일정을 해석하는 지역
    # 시간대로만 쓰인다(하드코딩 대신 설정 TIME_ZONE 일원화).
    timezone=timezone_settings.TIME_ZONE,
    enable_utc=True,
    beat_schedule={},
)
