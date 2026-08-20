"""Reports 도메인 ORM 모델 — **스키마 소유 전용**.

이 모델의 역할은 하나다: `sales_orders` 테이블을 App Registry 와 Alembic 이 알게
하는 것. 조회는 이 모델로 하지 않는다.

왜 모델을 두는가:
    Raw 조회만 한다고 모델을 만들지 않으면, 이 저장소가 migration 으로 만드는
    테이블이 registry metadata 에 없게 된다. 그러면 `alembic check` 가 "지워야 할
    테이블"로 보고 drift 를 만들고, registry-model 동등성 검사도 깨진다.

왜 조회에 쓰지 않는가:
    이 예제의 요점이 **Raw 집계**다. 집계 결과(일자별 합계)는 어떤 테이블의 행도
    아니다 — 그것을 ORM entity 로 표현하려면 실재하지 않는 모델을 지어내야 한다.
    그래서 결과는 ``RowMapping`` 으로 받아 Pydantic DTO 로 검증한다(RAW-REP-005).

.. note::
   Raw UPDATE 는 ``UpdatedAtMixin.onupdate`` 를 발동시키지 않는다 — 그건 ORM 이
   UPDATE 를 낼 때만 동작한다. Raw 로 갱신할 때는 SQL 에 ``updated_at`` 을 직접 쓴다.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base
from app.core.models.models_base import TimestampMixin, UUIDPrimaryKeyMixin


class SalesOrder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """매출 원본 주문 — 집계 SQL 이 읽는 테이블.

    Attributes:
        id: UUID 기본키
        order_no: 주문 번호(전역 고유)
        customer: 주문자
        total_amount: 주문 총액
        status: 주문 상태 (``paid`` 만 집계 대상)
        ordered_at: 주문 시각 — 집계 기준 컬럼
        created_at: 생성 시각
        updated_at: 수정 시각
    """

    __tablename__ = "sales_orders"

    order_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    customer: Mapped[str] = mapped_column(String(100), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="paid")
    # 집계 기준 컬럼. 인덱스가 없으면 리포트가 전체 스캔이 된다 — 기간 조회가
    # 이 컬럼의 범위 조건 하나로 결정되기 때문이다.
    ordered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<SalesOrder(id={self.id}, order_no={self.order_no!r})>"
