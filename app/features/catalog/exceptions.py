"""Catalog 도메인 예외."""

from enum import StrEnum

from app.core.exception import NotFoundException


class CatalogErrorCode(StrEnum):
    """Catalog 도메인 에러 코드 (네이밍: CATALOG_{대상}_{원인})."""

    PRODUCT_NOT_FOUND = "CATALOG_PRODUCT_NOT_FOUND"


class ProductNotFoundException(NotFoundException):
    """상품을 찾을 수 없는 경우."""

    error_code = CatalogErrorCode.PRODUCT_NOT_FOUND
    message = "상품을 찾을 수 없습니다."
