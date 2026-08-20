"""add sales_orders for the Raw SQL example

Revision ID: d1f8c4a70b93
Revises: c7d3e91b5a20
Create Date: 2026-08-19 00:00:01.000000

`reports` 예제(Raw SQL)가 집계하는 **원본** 테이블. 이 저장소가 소유하므로 migration
과 ORM 스키마 모델(`SalesOrder`)을 모두 둔다 — 그래야 registry-model/metadata 동등성
과 `alembic check` drift 검사가 유지된다. 조회는 여전히 Raw SQL 이 한다.

`ordered_at` 에 인덱스를 두는 이유: 리포트 쿼리가 이 컬럼의 범위 조건 하나로
행을 고른다. 인덱스가 없으면 기간 조회가 전체 스캔이 된다.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd1f8c4a70b93'
down_revision: str | Sequence[str] | None = 'c7d3e91b5a20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — create sales_orders."""
    op.create_table(
        'sales_orders',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('order_no', sa.String(length=32), nullable=False),
        sa.Column('customer', sa.String(length=100), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_no'),
    )
    op.create_index('ix_sales_orders_ordered_at', 'sales_orders', ['ordered_at'], unique=False)


def downgrade() -> None:
    """Downgrade schema — drop sales_orders."""
    op.drop_index('ix_sales_orders_ordered_at', table_name='sales_orders')
    op.drop_table('sales_orders')
