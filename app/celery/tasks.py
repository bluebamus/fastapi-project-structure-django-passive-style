"""중앙 Celery 태스크 모듈.

앱별 worker/ 를 대체하는 단일 태스크 모듈. 도메인 백그라운드 작업을 여기 정의한다.
celery_app.conf.include = ["app.celery.tasks"] 로 등록된다.
요청 밖 세션은 background_session 컨텍스트로 관리한다(UnitOfWork 제거).
"""

from app.celery.app import celery_app
from app.celery.task import run_async
from app.core.db.session import background_session
from app.features.home.services.user_access_log_service import UserAccessLogService
from config import middleware_settings


@celery_app.task(name="home.aggregate_access_stats")
def aggregate_access_stats() -> dict:
    """접속 로그 통계를 집계하여 반환한다(예시 태스크)."""

    async def _run() -> dict:
        async with background_session() as session:
            stats = await UserAccessLogService(session).get_stats()
            return {"total": stats.total_count}

    return run_async(_run())


@celery_app.task(name="home.purge_old_access_logs")
def purge_old_access_logs(days: int | None = None) -> dict:
    """보존 기간이 지난 접속 로그를 삭제한다.

    스케줄러(celery beat 등)가 주기적으로 호출하는 것을 전제로 한다. 반복 실행해도
    안전하다 — 지울 것이 없으면 0 을 반환한다.

    Args:
        days: 보존 일수. 생략하면 ACCESS_LOG_RETENTION_DAYS 설정을 쓴다.

    Returns:
        ``{"deleted": <삭제 건수>, "retention_days": <적용된 보존 일수>}``
    """
    retention = days if days is not None else middleware_settings.ACCESS_LOG_RETENTION_DAYS

    async def _run() -> dict:
        async with background_session() as session:
            deleted = await UserAccessLogService(session).purge_logs_older_than(retention)
            return {"deleted": deleted, "retention_days": retention}

    return run_async(_run())
