"""Catalog 도메인 ORM 모델.

**ORM 예제의 데이터 정의**다. Repository 가 이 모델로 조회·변경하고, Alembic 이
`catalog_products` 테이블을 소유한다.

Raw 예제(`reports`)와의 차이는 여기서 시작한다 — 저쪽도 `sales_orders` 테이블의
스키마 모델을 두지만, **조회 결과로는 쓰지 않는다**(RowMapping 을 쓴다).
"""

from decimal import Decimal

from sqlalchemy import Boolean, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import TimestampMixin, UUIDPrimaryKeyMixin


class Product(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """판매 상품.

    Attributes:
        id: UUID 기본키
        sku: 재고 관리 코드 (전역 고유)
        name: 상품명
        description: 설명(선택)
        price: 판매가
        stock: 재고 수량
        is_active: 판매 여부
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "catalog_products"

    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 돈은 float 로 두지 않는다 — 0.1 + 0.2 가 0.3 이 아닌 세계에서 잔액을 맞출 수 없다.
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, sku={self.sku!r})>"
