"""Catalog 기능 SQLAdmin 설정 — 상품 관리 화면.

Note:
    SQLAdmin 은 ``ADMIN_DISABLED`` 설정으로 제어된다(DEBUG 와 독립적). 이 앱이
    ``config.INSTALLED_APPS`` 에 없으면 이 파일이 있어도 등록되지 않는다.
"""

from sqladmin import ModelView
from sqladmin.filters import BooleanFilter

from app.core.admin_filters import LocalDateFilter
from app.features.catalog.models.models import Product


class ProductAdmin(ModelView, model=Product):
    """상품 관리자 뷰."""

    name = "상품"
    name_plural = "상품"
    icon = "fa-solid fa-box"

    # 설명(description)은 Text 컬럼이라 목록에서 제외한다(상세에서 확인).
    column_list = [
        Product.id,
        Product.sku,
        Product.name,
        Product.price,
        Product.stock,
        Product.is_active,
        Product.updated_at,
    ]

    column_default_sort = [(Product.sku, False)]

    page_size = 50
    page_size_options = [25, 50, 100, 200]

    column_searchable_list = [Product.sku, Product.name]
    # 필터는 sqladmin.filters 객체로 준다 — 컬럼을 그대로 넘기면 sqladmin 0.32 목록 처리가
    # ``parameter_name`` 을 찾다 AttributeError(목록 500)로 죽는다(admin-login F-007).
    # 시각 컬럼(UTCDateTime)은 sqladmin 연산 필터 대신 ``LocalDateFilter`` 로 건다 — 연산 필터는
    # UTCDateTime 을 날짜로 인식하지 못해 문자열을 바인딩한다(security-ops-hardening ADR-005).
    column_filters = [
        BooleanFilter(Product.is_active),
        LocalDateFilter(Product.created_at, title="생성일"),
    ]

    column_details_list = [
        Product.id,
        Product.sku,
        Product.name,
        Product.description,
        Product.price,
        Product.stock,
        Product.is_active,
        Product.created_at,
        Product.updated_at,
    ]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
    can_export = True
    export_types = ["csv", "json"]

    # id 는 UUID 기본값으로, 시각 컬럼은 모델의 default/onupdate 로 채워진다.
    form_excluded_columns = [Product.id, Product.created_at, Product.updated_at]

    column_labels = {
        Product.id: "ID",
        Product.sku: "SKU",
        Product.name: "상품명",
        Product.description: "설명",
        Product.price: "판매가",
        Product.stock: "재고",
        Product.is_active: "판매 여부",
        Product.created_at: "생성 시각",
        Product.updated_at: "수정 시각",
    }


admin_views: list[type] = [ProductAdmin]
