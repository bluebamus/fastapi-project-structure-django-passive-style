"""Reports v1 API — 일별 매출 리포트 (**Raw SQL 예제**).

ORM 예제의 View(`app/features/catalog/api/routers/v1/products.py`)와 구조가 같다.
데이터가 Raw SQL 에서 왔다는 사실은 이 파일 어디에도 나타나지 않는다 — 그것이
ADR-002 가 요구하는 상태다.

조회 전용이므로 커밋하지 않는다.
"""

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.exception import ErrorResponse
from app.features.reports.dependencies.reports_dependencies import (
    get_report_service_readonly,
)
from app.features.reports.schemas.report_schema import DailySalesReportResponse
from app.features.reports.services.report_service import ReportService

router = APIRouter()

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
    operation_id="getDailySalesReport",
)
async def get_daily_sales_report(
    start_date: date = Query(..., description="조회 시작일(포함)", examples=["2026-08-01"]),
    end_date: date = Query(..., description="조회 종료일(포함)", examples=["2026-08-07"]),
    service: ReportService = Depends(get_report_service_readonly),
) -> DailySalesReportResponse:
    return await service.daily_sales_report(start_date=start_date, end_date=end_date)
