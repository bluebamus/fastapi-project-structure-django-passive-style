"""Catalog Service — 상품 비즈니스 규칙.

세션을 주입받아 Repository 를 구성한다. **커밋하지 않는다** — 트랜잭션 경계는
쓰기 View 본문이 소유한다(ADR-008). Raw 예제의 Service 와 이 점이 동일하다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.services.services_base import BaseService
from app.features.catalog.exceptions import ProductNotFoundException
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.product_schema import ProductCreate, ProductUpdate


class CatalogService(BaseService):
    """상품 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.repository = ProductRepository(session)

    async def create_product(self, data: ProductCreate) -> Product:
        """상품을 생성한다(커밋은 호출자가 수행)."""
        self.log.debug("상품 생성: sku=%s", data.sku)
        return await self.repository.create(data.model_dump())

    async def get_product(self, product_id: str) -> Product:
        """상품을 조회한다. 없으면 ProductNotFoundException."""
        product = await self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundException(detail={"id": product_id})
        return product

    async def list_products(
        self,
        *,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
    ) -> tuple[Sequence[Product], int]:
        """상품 목록과 전체 개수를 조회한다."""
        if active_only:
            products = await self.repository.get_active(skip=skip, limit=limit)
        else:
            products = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return products, total

    async def update_product(self, product_id: str, data: ProductUpdate) -> Product:
        """상품을 부분 수정한다. 없으면 ProductNotFoundException."""
        existing = await self.get_product(product_id)  # 존재 보장(없으면 404)
        payload = data.model_dump(exclude_unset=True)
        if not payload:
            return existing
        updated = await self.repository.update(product_id, payload)
        return updated if updated is not None else existing

    async def delete_product(self, product_id: str) -> None:
        """상품을 삭제한다. 없으면 ProductNotFoundException."""
        deleted = await self.repository.delete(product_id)
        if not deleted:
            raise ProductNotFoundException(detail={"id": product_id})
