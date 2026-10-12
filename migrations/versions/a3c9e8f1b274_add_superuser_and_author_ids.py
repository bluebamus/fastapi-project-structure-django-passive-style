"""add users.is_superuser and author_id on blog/sns/reply

Revision ID: a3c9e8f1b274
Revises: e5a7c2d9f310
Create Date: 2026-10-12 00:00:00.000000

인가 정책(service-hardening 단계 F2 · ADR-018·ADR-019).

* ``users.is_superuser`` — 슈퍼유저/일반 2단계 권한. 기존 사용자는 ``server_default`` 로
  ``false`` 가 된다(아무도 자동으로 관리자가 되지 않는다 — 첫 관리자는
  ``scripts/create_superuser.py`` 로 만든다).
* ``blog_posts``·``sns_posts``·``replies`` 의 ``author_id`` — 소유자 판정 키. 기존 행은
  작성자를 알 수 없으므로 ``NULL`` 이고, ``NULL`` 행은 슈퍼유저만 수정·삭제할 수 있다.
  FK 를 걸지 않는다 — 사용자 삭제가 게시물 삭제를 강제하지 않게 하고, 기존 ``post_id`` 처럼
  기능 간 느슨한 참조를 유지한다.

새 컬럼은 테이블 끝에 붙는다(MySQL ``ADD COLUMN`` 기본). 모델 정의의 배치(도메인 컬럼 뒤,
``created_at`` 앞)와 물리 순서가 다를 수 있으나 이름으로 접근하므로 동작에는 영향이 없다 —
``users.hashed_password`` 리비전(b2f1a9c0d3e4)과 같은 방식이다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3c9e8f1b274'
down_revision: str | Sequence[str] | None = 'e5a7c2d9f310'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_AUTHORED_TABLES = ('blog_posts', 'sns_posts', 'replies')


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('is_superuser', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    for table in _AUTHORED_TABLES:
        op.add_column(table, sa.Column('author_id', sa.String(length=36), nullable=True))
        op.create_index(op.f(f'ix_{table}_author_id'), table, ['author_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    for table in reversed(_AUTHORED_TABLES):
        op.drop_index(op.f(f'ix_{table}_author_id'), table_name=table)
        op.drop_column(table, 'author_id')
    op.drop_column('users', 'is_superuser')
