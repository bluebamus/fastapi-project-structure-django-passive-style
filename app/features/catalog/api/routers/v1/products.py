"""Catalog v1 API — 상품 CRUD (**ORM 예제**).

View 는 HTTP 역할만 한다: 파라미터 수신 → 주입된 Service 호출 → 응답 DTO 변환.
쓰기는 응답을 만들기 **전에** 한 번 커밋한다(ADR-008).

Raw 예제의 View(`app/features/reports/api/routers/v1/sales_reports.py`)와 이 파일을
비교하면, 달라지는 것이 Repository 뿐임이 드러난다.
"""

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from app.core.exception import ErrorResponse
from app.features.catalog.dependencies.catalog_dependencies import (
    get_catalog_service,
    get_catalog_service_readonly,
)
from app.features.catalog.schemas.product_schema import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)
from app.features.catalog.services.catalog_service import CatalogService

router = APIRouter()

_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "상품을 찾을 수 없음"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "이미 존재하는 SKU"}
}


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CONFLICT,
    summary="상품 생성",
    description="새 상품을 등록합니다. `sku` 는 전역 고유해야 합니다.",
    operation_id="createProduct",
)
async def create_product(
    payload: ProductCreate,
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.create_product(payload)
    await service.commit()
    return ProductResponse.model_validate(product)


@router.get(
    "/products",
    response_model=ProductListResponse,
    summary="상품 목록 조회",
    description="상품 목록을 페이지네이션하여 조회합니다. SKU 오름차순으로 안정 정렬됩니다.",
    operation_id="listProducts",
)
async def list_products(
    skip: int = Query(0, ge=0, description="건너뛸 레코드 수(offset)"),
    limit: int = Query(50, ge=1, le=100, description="조회할 레코드 수(1-100)"),
    active_only: bool = Query(False, description="판매 중인 상품만 조회"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductListResponse:
    products, total = await service.list_products(skip=skip, limit=limit, active_only=active_only)
    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses=_NOT_FOUND,
    summary="상품 단건 조회",
    description="ID 로 상품을 조회합니다.",
    operation_id="getProduct",
)
async def get_product(
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service_readonly),
) -> ProductResponse:
    product = await service.get_product(product_id)
    return ProductResponse.model_validate(product)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses=_NOT_FOUND,
    summary="상품 수정",
    description="상품을 부분 수정합니다(전달한 필드만).",
    operation_id="updateProduct",
)
async def update_product(
    payload: ProductUpdate,
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> ProductResponse:
    product = await service.update_product(product_id, payload)
    await service.commit()
    return ProductResponse.model_validate(product)


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND,
    summary="상품 삭제",
    description="상품을 삭제합니다.",
    operation_id="deleteProduct",
)
async def delete_product(
    product_id: str = Path(..., description="상품 ID(UUID)"),
    service: CatalogService = Depends(get_catalog_service),
) -> None:
    await service.delete_product(product_id)
    await service.commit()
