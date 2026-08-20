"""Product Repository — **ORM 데이터 접근**.

`BaseRepository` 의 최소 CRUD 8개(ADR-016)를 그대로 쓴다. 도메인 전용 조회가
필요해지면 Base 를 넓히지 않고 **여기에** 추가한다 — Base 를 넓히면 Raw 쪽에서도
같은 것을 다시 구현해야 한다.

Raw 대응물은 `app/features/reports/repositories/sales_report_repository.py` 다.
두 파일을 나란히 놓으면 이 프로젝트에서 ORM 과 Raw 가 갈리는 지점이 정확히
**Repository 하나**임이 보인다.
"""

from collections.abc import Sequence

from sqlalchemy import select

from app.core.repositories.repository_base import BaseRepository
from app.features.catalog.models.models import Product


class ProductRepository(BaseRepository[Product]):
    """상품 Repository (ORM)."""

    model = Product

    async def get_active(self, *, skip: int = 0, limit: int = 50) -> Sequence[Product]:
        """판매 중인 상품만 조회한다 — 도메인 전용 쿼리의 배치 예시.

        정렬 키를 주는 이유는 pagination 때문이다. 정렬이 없으면 DB 가 페이지마다
        다른 순서를 돌려줄 수 있어 같은 행이 두 페이지에 나오거나 아예 빠진다.
        """
        statement = (
            select(Product)
            .where(Product.is_active.is_(True))
            .order_by(Product.sku)
            .offset(skip)
            .limit(limit)
        )
        return (await self.session.execute(statement)).scalars().all()
