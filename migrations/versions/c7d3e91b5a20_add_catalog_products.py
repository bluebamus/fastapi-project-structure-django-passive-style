"""add catalog_products for the ORM example

Revision ID: c7d3e91b5a20
Revises: b2f1a9c0d3e4
Create Date: 2026-08-19 00:00:00.000000

`catalog` 예제(ORM)가 소유하는 테이블. 컬럼 배치는 모델과 같다 —
id → 도메인 컬럼 → created_at → updated_at (ADR-014). Alembic 은 컬럼을 이름으로
비교해 순서를 diff 로 잡지 않으므로, 여기서 어긋나면 `create_all` 로 만든 개발 DB 와
아무 경고 없이 갈린다.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c7d3e91b5a20'
down_revision: str | Sequence[str] | None = 'b2f1a9c0d3e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema — create catalog_products."""
    op.create_table(
        'catalog_products',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sku', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        # 돈은 Numeric 이다. Float 로 두면 합계가 조용히 틀어진다.
        sa.Column('price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('stock', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sku'),
    )


def downgrade() -> None:
    """Downgrade schema — drop catalog_products."""
    op.drop_table('catalog_products')
