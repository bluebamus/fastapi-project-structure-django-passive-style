"""baseline 마이그레이션이 **MySQL** 에서도 모델과 같은 스키마를 만들고 깨끗이 되돌린다.

SQLite 판(``tests/core/db/test_migrations.py``)이 못 보는 것: MySQL 방언의 DDL(``DATETIME(6)`` variant·
``utf8mb4`` 인덱스 길이·유니크 인덱스 반영)과 MySQL 리플렉션으로 본 autogenerate diff.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy.engine import URL

from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS


def test_upgrade_head_matches_models_and_downgrade_base_is_clean(mysql_url: URL, monkeypatch):
    import config as config_module

    sync_url = mysql_url.set(drivername="mysql+pymysql")
    # env.py 는 실행 시점의 db_settings.ALEMBIC_URL 을 읽는다 — 테스트 DB 로 돌린다.
    monkeypatch.setattr(
        config_module.db_settings,
        "ALEMBIC_DATABASE_URL",
        sync_url.render_as_string(hide_password=False),
    )
    alembic_config = Config("alembic.ini")
    Apps().populate(INSTALLED_APPS, run_ready=False)
    engine = sa.create_engine(sync_url)
    try:
        command.upgrade(alembic_config, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
            precision = conn.execute(
                sa.text(
                    "SELECT DATETIME_PRECISION FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'sales_orders' "
                    "AND COLUMN_NAME = 'ordered_at'"
                )
            ).scalar_one()
        assert diff == [], f"MySQL 의 마이그레이션 결과와 모델이 다르다: {diff}"
        assert precision == 6  # UTCDateTime → DATETIME(6)

        command.downgrade(alembic_config, "base")
        assert set(sa.inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
