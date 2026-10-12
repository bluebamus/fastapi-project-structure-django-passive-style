"""Home 기능의 Celery 태스크.

워커는 ``AppConfig.tasks_module``(기본 ``"tasks"``)로 이 module 을 찾아 include 한다
(service-hardening ADR-012). 요청 밖이므로 세션은 ``background_session()`` 이 열고,
서비스 조립은 HTTP 경로와 같은 provider 함수에 맡긴다 — 조립 규칙이 한 곳에 있다.
"""

from typing import Any

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_session
from app.features.home.dependencies.access_log_dependencies import (
    build_user_access_log_service,
)


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict[str, Any]:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict[str, Any]:
        async with background_session() as session:
            stats = await build_user_access_log_service(session).get_stats()
            return {"total": stats.total_count}

    result: dict[str, Any] = run_async(_run())
    return result
