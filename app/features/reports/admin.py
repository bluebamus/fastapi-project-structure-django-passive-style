"""Reports 기능 SQLAdmin 설정 — 매출 원본 주문 조회 화면.

**읽기 전용이다.** 이 테이블은 다른 시스템이 채우는 원본 데이터이고, 리포트의
집계 결과가 여기서 나온다. Admin 에서 손으로 고치면 집계가 조용히 달라지므로
생성·수정·삭제를 모두 막았다.

집계 **결과**는 여기 없다. 결과는 어떤 테이블의 행도 아니라 Raw SQL 이 만들어내는
값이고, 그건 `/api/v1/reports/daily-sales` 가 답한다.
"""

from sqladmin import ModelView
from sqladmin.filters import OperationColumnFilter

from app.core.admin_filters import LocalDateFilter
from app.features.reports.models.models import SalesOrder


class SalesOrderAdmin(ModelView, model=SalesOrder):
    """매출 원본 주문 뷰 (읽기 전용)."""

    name = "매출 주문"
    name_plural = "매출 주문"
    icon = "fa-solid fa-receipt"

    column_list = [
        SalesOrder.id,
        SalesOrder.order_no,
        SalesOrder.customer,
        SalesOrder.total_amount,
        SalesOrder.status,
        SalesOrder.ordered_at,
    ]

    column_default_sort = [(SalesOrder.ordered_at, True)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [SalesOrder.order_no, SalesOrder.customer]
    # 필터는 sqladmin.filters 객체로 준다 — 컬럼을 그대로 넘기면 sqladmin 0.32 목록 처리가
    # ``parameter_name`` 을 찾다 AttributeError(목록 500)로 죽는다(admin-login F-007).
    # 시각 컬럼(UTCDateTime)은 sqladmin 연산 필터 대신 ``LocalDateFilter`` 로 건다 — 연산 필터는
    # UTCDateTime 을 날짜로 인식하지 못해 문자열을 바인딩한다(security-ops-hardening ADR-005).
    column_filters = [
        OperationColumnFilter(SalesOrder.status),
        LocalDateFilter(SalesOrder.created_at, title="생성일"),
    ]

    column_details_list = [
        SalesOrder.id,
        SalesOrder.order_no,
        SalesOrder.customer,
        SalesOrder.total_amount,
        SalesOrder.status,
        SalesOrder.ordered_at,
        SalesOrder.created_at,
        SalesOrder.updated_at,
    ]

    # 원본 데이터를 화면에서 고치면 리포트 숫자가 근거 없이 움직인다.
    can_create = False
    can_edit = False
    can_delete = False
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    column_labels = {
        SalesOrder.id: "ID",
        SalesOrder.order_no: "주문 번호",
        SalesOrder.customer: "주문자",
        SalesOrder.total_amount: "주문 총액",
        SalesOrder.status: "상태",
        SalesOrder.ordered_at: "주문 시각",
        SalesOrder.created_at: "생성 시각",
        SalesOrder.updated_at: "수정 시각",
    }


admin_views: list[type] = [SalesOrderAdmin]
