"""store datetimes as UTC with microseconds

!! 배포 전 확인 (MySQL 운영 DB) !!
* 이 리비전은 기존 MySQL 시각 값이 ``+09:00``(KST 벽시계)으로 저장됐다고 **가정**하고 UTC 로
  옮긴다. 다른 시간대로 운영했던 DB 라면 적용 전에 아래 ``LEGACY_OFFSET`` 상수를 그 오프셋으로
  바꾼다(틀린 오프셋으로 올리면 모든 시각이 그만큼 어긋난 채 저장된다).
* 적용 전에 반드시 백업한다 — ``UPDATE`` 로 값을 다시 쓰므로 되돌리려면 백업이나 정확한
  downgrade 가 필요하다.

Revision ID: e5a7c2d9f310
Revises: d1f8c4a70b93
Create Date: 2026-10-12 00:00:00.000000

시각 정책 변경(service-hardening ADR-010 · C-9). 모델의 ``Mapped[datetime]`` 이
``UTCDateTime`` 이 되면서 MySQL 컬럼은 ``DATETIME(6)``(마이크로초), 값은 **UTC** 다.

MySQL 에서 하는 일(컬럼마다):

1. ``MODIFY ... DATETIME(6) NOT NULL`` — 기존 값은 그대로, 소수부 ``.000000`` 이 붙는다.
   모든 시각 컬럼이 NOT NULL 이므로 nullability 가 그대로다.
2. ``UPDATE ... SET col = CONVERT_TZ(col, '+09:00', '+00:00')`` — 이전 코드가 쓴 값은
   설정 ``TIME_ZONE`` 의 **벽시계**였다(드라이버가 aware 값의 tzinfo 를 떼고 보낸다).
   기본값 Asia/Seoul 을 전제로 KST → UTC 로 옮긴다. **가정:** Asia/Seoul 은 1988년 이후
   DST 가 없어 오프셋이 항상 +09:00 이다. 다른 ``TIME_ZONE`` 으로 운영했던 DB 는 이
   리비전 전에 오프셋을 바꿔야 한다. 숫자 오프셋이라 MySQL 시간대 테이블이 필요 없다.
   ``CONVERT_TZ`` 는 TIMESTAMP 범위(1970-01-01 ~ 3001-01-18 UTC) 밖의 값은 바꾸지 않는다.

downgrade 는 역순이다 — UTC → +09:00 으로 되돌린 뒤 ``DATETIME`` 으로 줄인다(소수부는
MySQL 규칙대로 반올림된다).

SQLite 는 no-op 이다 — 타입 이름이 그대로 ``DATETIME`` 이고 값의 시간대를 옮길 운영
데이터가 없다(단위 테스트·드리프트 검사용).

큰 테이블에서는 ``ALTER``·``UPDATE`` 가 테이블을 다시 쓴다. 배포 창에서 돌린다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = 'e5a7c2d9f310'
down_revision: str | Sequence[str] | None = 'd1f8c4a70b93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: 이 시점의 모든 시각 컬럼(전부 NOT NULL). 테이블·컬럼 이름은 코드 상수다.
DATETIME_COLUMNS: dict[str, tuple[str, ...]] = {
    'user_access_logs': ('created_at',),
    'users': ('created_at', 'updated_at'),
    'blog_posts': ('created_at', 'updated_at'),
    'replies': ('created_at', 'updated_at'),
    'sns_posts': ('created_at', 'updated_at'),
    'catalog_products': ('created_at', 'updated_at'),
    'sales_orders': ('ordered_at', 'created_at', 'updated_at'),
}

#: 이전 코드가 쓴 벽시계의 오프셋(설정 TIME_ZONE 기본값 Asia/Seoul, DST 없음).
LEGACY_OFFSET = '+09:00'


def _convert(table: str, columns: tuple[str, ...], from_tz: str, to_tz: str) -> None:
    # 식별자는 위 상수뿐이다(요청값이 아니다). 오프셋도 상수라 bind 할 값이 없다.
    assignments = ', '.join(
        f"`{column}` = CONVERT_TZ(`{column}`, '{from_tz}', '{to_tz}')" for column in columns
    )
    op.execute(f'UPDATE `{table}` SET {assignments}')


def upgrade() -> None:
    """MySQL: DATETIME(6) 로 넓히고 KST 벽시계를 UTC 로 옮긴다. SQLite: no-op."""
    if op.get_bind().dialect.name != 'mysql':
        return
    for table, columns in DATETIME_COLUMNS.items():
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=mysql.DATETIME(),
                type_=mysql.DATETIME(fsp=6),
                existing_nullable=False,
            )
        _convert(table, columns, LEGACY_OFFSET, '+00:00')


def downgrade() -> None:
    """MySQL: UTC 를 KST 벽시계로 되돌리고 DATETIME 으로 줄인다. SQLite: no-op."""
    if op.get_bind().dialect.name != 'mysql':
        return
    for table, columns in DATETIME_COLUMNS.items():
        _convert(table, columns, '+00:00', LEGACY_OFFSET)
        for column in columns:
            op.alter_column(
                table,
                column,
                existing_type=mysql.DATETIME(fsp=6),
                type_=sa.DateTime(),
                existing_nullable=False,
            )
