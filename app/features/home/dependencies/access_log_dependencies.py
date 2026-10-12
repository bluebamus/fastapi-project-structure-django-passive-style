"""Home 접속 로그 기능 의존성 (인터페이스 집합체).

home 은 조회 엔드포인트만 가진다(쓰기 없음). 접속 로그 적재는 미들웨어가
`background_session()` 으로 따로 처리하므로, 이 의존성은 커밋할 이유가 없다.

따라서 읽기 전용 세션을 쓴다 — 조회마다 발생하던 불필요한 COMMIT 왕복이 사라지고,
`DB_ROUTER_ENABLED` 가 켜지면 replica 로 라우팅된다. 읽기 핸들러가 몰래 쓰기를
시도하면 `ReadOnlyRoutingError` 로 즉시 실패한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.home.services.user_access_log_service import UserAccessLogService
from config import timezone_settings


def build_user_access_log_service(session: AsyncSession) -> UserAccessLogService:
    """세션 하나로 UserAccessLogService 를 조립한다 — HTTP·Celery 공용 조립 규칙.

    세션의 출처(요청 의존성 / ``background_session()``)는 호출자가 정한다.
    """
    return UserAccessLogService(session, timezone_settings)


async def get_access_log_service(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> UserAccessLogService:
    """UserAccessLogService 를 구성해 view 에 제공한다(읽기 전용 — 커밋하지 않는다)."""
    return build_user_access_log_service(session)
