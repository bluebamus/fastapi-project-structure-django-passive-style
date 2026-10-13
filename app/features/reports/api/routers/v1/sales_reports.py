"""Reports v1 API — 일별 매출 리포트 (**Raw SQL 예제**).

ORM 예제의 View(`app/features/catalog/api/routers/v1/products.py`)와 구조가 같다.
데이터가 Raw SQL 에서 왔다는 사실은 이 파일 어디에도 나타나지 않는다 — 그것이
ADR-002 가 요구하는 상태다.

조회 전용이므로 커밋하지 않는다. 매출은 운영 정보라 슈퍼유저만 본다(뷰 선언 ``SuperuserRequired``).
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.exception import ErrorResponse
from app.core.security.access import SuperuserRequired
from app.core.security.dependencies import (
    ADMIN_FORBIDDEN_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)
from app.features.reports.dependencies.reports_dependencies import (
    get_report_service_readonly,
)
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

#: 모든 엔드포인트가 슈퍼유저 전용이다(service-hardening F2) — 접근 수준은 뷰마다 선언한다
#: (access-policy). 401/403 응답 문서만 라우터에서 한 번에 싣는다.
router = APIRouter(
    responses={**UNAUTHORIZED_RESPONSE, **ADMIN_FORBIDDEN_RESPONSE},
)

_BAD_RANGE: dict[int | str, dict[str, Any]] = {
    422: {"model": ErrorResponse, "description": "조회 기간이 올바르지 않음"}
}


@router.get(
    "/daily-sales",
    response_model=DailySalesReportResponse,
    responses=_BAD_RANGE,
    summary="일별 매출 리포트",
    description=(
        "기간 내 일자별 주문 수와 매출 합계를 조회합니다. "
        "종료일은 **포함**이며, 결제 완료(`paid`) 주문만 집계합니다."
    ),
    dependencies=[SuperuserRequired],
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(..., description="조회 시작일(포함)", examples=["2026-08-01"]),
    end_date: date = Query(..., description="조회 종료일(포함)", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    return await service.daily_sales_report(start_date=start_date, end_date=end_date)
