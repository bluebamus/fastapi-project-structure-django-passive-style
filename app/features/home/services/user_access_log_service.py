"""
UserAccessLog Service

접속 로그 관련 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계: 요청 경로는 핸들러가, 요청 밖(sink·Celery 태스크)은 background_session() 이 맡는다.
예외는 ``purge_expired`` — 잠금을 짧게 하려고 배치마다 스스로 커밋한다.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import String
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.home.exceptions import InvalidDateRangeException
from app.features.home.models.models import UserAccessLog
from app.features.home.repositories.user_access_log_repository import UserAccessLogRepository
from app.features.home.schemas.user_access_log_schema import (
    AccessLogStats,
    BrowserStats,
    DeviceTypeStats,
    OSStats,
    UserAccessLogCreate,
)
from config import TimezoneSettings, timezone_settings

#: 문자열 컬럼의 최대 길이 — 모델 선언에서 읽는다(숫자를 두 번 적지 않는다, ADR-006).
#: 길이가 없는 ``Text`` 는 빠진다.
_COLUMN_MAX_LENGTHS: dict[str, int] = {
    column.name: column.type.length
    for column in UserAccessLog.__table__.columns
    if isinstance(column.type, String) and column.type.length
}

#: 보존 삭제 한 번(트랜잭션 하나)에 지우는 최대 행 수 — 긴 잠금·거대한 트랜잭션을 피한다.
PURGE_BATCH_SIZE = 5_000


def truncate_to_columns(data: dict[str, Any]) -> dict[str, Any]:
    """문자열 값을 ``user_access_logs`` 컬럼 길이로 자른 새 dict 를 돌려준다.

    헤더·쿠키는 클라이언트가 정하므로 길이를 믿을 수 없다. 자르지 않으면 MySQL strict 모드가
    1406(Data too long)으로 INSERT 를 거부하고, 긴 헤더 하나로 접속 기록을 피할 수 있다.
    """
    return {
        key: value[: _COLUMN_MAX_LENGTHS[key]]
        if isinstance(value, str) and key in _COLUMN_MAX_LENGTHS
        else value
        for key, value in data.items()
    }


class UserAccessLogService(BaseService):
    """접속 로그 비즈니스 로직 (세션 기반)."""

    def __init__(
        self,
        session: AsyncSession,
        timezone: TimezoneSettings = timezone_settings,
        retention_days: int = 0,
    ) -> None:
        super().__init__(session)
        self.repository = UserAccessLogRepository(session)
        self.timezone = timezone
        #: 보존 일수(``ACCESS_LOG_RETENTION_DAYS``) — provider 가 설정에서 넣는다. 0 = 지우지 않음.
        self.retention_days = retention_days

    async def create_access_log(
        self,
        data: UserAccessLogCreate | dict[str, Any],
    ) -> UserAccessLog:
        """접속 로그를 생성한다(커밋은 호출자가 수행). 문자열은 컬럼 길이로 자른다."""
        data_dict = truncate_to_columns(
            data.model_dump() if isinstance(data, UserAccessLogCreate) else data
        )
        self.log.debug("접속 로그 생성: path=%s", data_dict.get("request_path"))
        return await self.repository.create(data_dict)

    async def get_access_logs(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[UserAccessLog], int]:
        """접속 로그 목록과 전체 개수를 조회한다."""
        self.log.debug("접속 로그 목록 조회: skip=%s, limit=%s", skip, limit)
        logs = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return logs, total

    async def get_recent_logs(self, limit: int = 50) -> Sequence[UserAccessLog]:
        """최근 접속 로그를 조회한다."""
        self.log.debug("최근 접속 로그 조회: limit=%s", limit)
        return await self.repository.get_recent_logs(limit=limit)

    async def get_logs_by_ip(
        self,
        ip_address: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """IP 주소로 접속 로그를 조회한다."""
        self.log.debug("IP별 접속 로그 조회: ip=%s", ip_address)
        return await self.repository.get_by_ip(ip_address=ip_address, skip=skip, limit=limit)

    async def get_logs_by_user(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """사용자 ID로 접속 로그를 조회한다."""
        self.log.debug("사용자별 접속 로그 조회: user_id=%s", user_id)
        return await self.repository.get_by_user_id(user_id=user_id, skip=skip, limit=limit)

    async def get_logs_by_date_range(
        self,
        start_date: date,
        end_date: date,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[UserAccessLog]:
        """날짜 범위(설정 시간대의 지역 일자, 양끝 포함)로 접속 로그를 조회한다.

        DB 는 UTC 로 저장하므로 지역 0시를 UTC 순간으로 바꿔 ``[시작일 0시, 종료일+1 0시)`` 로
        조회한다 — Asia/Seoul 의 10월 12일은 ``[10-11T15:00Z, 10-12T15:00Z)`` 다.
        """
        if start_date > end_date:
            self.log.warning("잘못된 날짜 범위: start=%s end=%s", start_date, end_date)
            raise InvalidDateRangeException(
                detail={"start_date": str(start_date), "end_date": str(end_date)},
            )
        self.log.debug("날짜 범위 접속 로그 조회: %s ~ %s", start_date, end_date)
        return await self.repository.get_by_date_range(
            start_at=self.timezone.local_midnight_utc(start_date),
            end_exclusive=self.timezone.local_midnight_utc(end_date + timedelta(days=1)),
            skip=skip,
            limit=limit,
        )

    async def get_stats(self) -> AccessLogStats:
        """접속 로그 통계를 조회한다."""
        self.log.debug("접속 로그 통계 조회 시작")
        total_count = await self.repository.count()
        device_counts = await self.repository.count_by_device_type()
        os_counts = await self.repository.count_by_os()
        browser_counts = await self.repository.count_by_browser()
        return AccessLogStats(
            total_count=total_count,
            device_types=[
                DeviceTypeStats(device_type=k, count=v) for k, v in device_counts.items()
            ],
            os_list=[OSStats(os_name=k, count=v) for k, v in os_counts.items()],
            browsers=[BrowserStats(browser_name=k, count=v) for k, v in browser_counts.items()],
        )

    async def purge_expired(
        self, *, now: datetime | None = None, batch_size: int = PURGE_BATCH_SIZE
    ) -> int:
        """보존 기간이 지난 접속 로그를 배치로 지우고 지운 총 행 수를 돌려준다.

        기준은 ``now - retention_days`` 이고 그보다 **오래된** 행만 지운다(정확히 그 순간의 행은
        남는다). 배치마다 커밋한다 — 한 트랜잭션으로 수백만 행을 지우면 잠금이 길어지고 실패 시
        전부 되돌아간다. ``retention_days`` 가 0 이면 DB 에 가지 않고 0 을 돌려준다.

        Args:
            now: 기준 시각(aware). 테스트가 시계를 주입한다 — 기본은 ``timezone.utc_now()``.
            batch_size: 한 번에 지울 최대 행 수.
        """
        if self.retention_days <= 0:
            return 0
        cutoff = (now or self.timezone.utc_now()) - timedelta(days=self.retention_days)
        total = 0
        while True:
            deleted = await self.repository.delete_created_before(cutoff, batch_size)
            await self.commit()
            total += deleted
            if deleted < batch_size:
                break
        self.log.info(
            "접속 로그 보존 삭제: deleted=%s cutoff=%s retention_days=%s",
            total,
            cutoff.isoformat(),
            self.retention_days,
        )
        return total
