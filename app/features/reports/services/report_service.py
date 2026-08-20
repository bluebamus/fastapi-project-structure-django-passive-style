"""Reports Service — 집계 규칙과 DTO 경계.

Raw Repository 가 돌려준 ``RowMapping`` 이 **여기서** Pydantic DTO 가 된다. View 는
Row 를 보지 않는다(RAW-REP-005).

기간 규칙도 여기 있다 — 뒤집힌 기간과 과도한 범위를 거부하고, 포함 종료일을
**배타 상한**으로 바꿔 Repository 에 넘긴다. 그 계산을 SQL 의 방언 함수
(``DATE_ADD``)에 맡기지 않는 이유는 repository 모듈 docstring 참조.
"""

from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.reports.exceptions import InvalidDateRangeException
from app.features.reports.repositories.sales_report_repository import (
    SalesReportRawRepository,
)
from app.features.reports.schemas.report_schema import (
    DailySalesItem,
    DailySalesReportResponse,
)

#: 한 번에 조회할 수 있는 최대 기간(일). 무제한 집계는 replica 를 통째로 묶는다.
MAX_RANGE_DAYS = 366


class ReportService(BaseService):
    """매출 리포트 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = SalesReportRawRepository(session)

    async def daily_sales_report(
        self, *, start_date: date, end_date: date
    ) -> DailySalesReportResponse:
        """일별 매출 리포트를 만든다. 조회이므로 커밋하지 않는다."""
        self._validate_range(start_date, end_date)
        # 포함 종료일 → 배타 상한. 이렇게 두면 그날의 23:59:59 주문이 빠지지 않는다.
        end_exclusive = end_date + timedelta(days=1)

        rows = await self.repository.daily_sales(start_at=start_date, end_exclusive=end_exclusive)
        total = await self.repository.order_count(start_at=start_date, end_exclusive=end_exclusive)

        return DailySalesReportResponse(
            start_date=start_date,
            end_date=end_date,
            order_count=total,
            # dict(row) 로 명시 변환한 뒤 검증한다 — RowMapping 을 그대로 흘리지 않는다.
            items=[DailySalesItem.model_validate(dict(row)) for row in rows],
        )

    @staticmethod
    def _validate_range(start_date: date, end_date: date) -> None:
        if end_date < start_date:
            raise InvalidDateRangeException(
                message="종료일이 시작일보다 앞섭니다.",
                detail={"start_date": str(start_date), "end_date": str(end_date)},
            )
        span = (end_date - start_date).days + 1
        if span > MAX_RANGE_DAYS:
            raise InvalidDateRangeException(
                message=f"조회 기간은 최대 {MAX_RANGE_DAYS}일입니다.",
                detail={"requested_days": span, "max_days": MAX_RANGE_DAYS},
            )
