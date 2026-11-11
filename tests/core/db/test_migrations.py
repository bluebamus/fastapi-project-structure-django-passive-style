"""마이그레이션 — 빈 DB 에 ``upgrade head`` 가 모델과 같은 스키마를 만들고 ``downgrade base`` 가 깨끗이 되돌린다.

운영(``DEBUG=false``)에서는 Alembic 이 유일한 스키마 경로다. SQLite 로 돌므로 외부 인프라가 필요 없다.
"""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS


def test_upgrade_matches_models_and_downgrade_is_clean(tmp_path, monkeypatch):
    import config as config_module

    url = f"sqlite:///{(tmp_path / 'migrations.db').as_posix()}"
    # env.py 는 실행 시점의 ``config.db_settings`` 를 읽는다 — 다른 테스트가 config 를 reload 했어도
    # 지금 모듈 속성을 patch 해야 alembic 이 ``.env`` 의 DB 가 아니라 이 파일로 간다.
    monkeypatch.setattr(config_module.db_settings, "ALEMBIC_DATABASE_URL", url)
    alembic_config = Config("alembic.ini")
    Apps().populate(INSTALLED_APPS, run_ready=False)
    engine = sa.create_engine(url)
    try:
        command.upgrade(alembic_config, "head")
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
        assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"

        command.downgrade(alembic_config, "base")
        assert set(sa.inspect(engine).get_table_names()) <= {"alembic_version"}
    finally:
        engine.dispose()
