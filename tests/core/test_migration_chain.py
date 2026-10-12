"""마이그레이션 체인이 빈 DB에서 끝까지 적용되는지 검증 (계획서 P4-2).

baseline 이 user_access_logs 하나만 만들고 나머지 도메인 테이블을 통째로 빠뜨려,
다음 리비전이 존재하지 않는 users 를 ALTER 하며 체인이 끊겨 있었다. DEBUG 모드의
create_db_tables() 가 이 결함을 가려왔다 — 운영(DEBUG=false)에서는 Alembic 이
유일한 스키마 경로이므로 배포가 불가능한 상태였다.

같은 사고가 다시 나지 않도록, 실제로 빈 DB에 `upgrade head` 를 돌려 결과 스키마가
모델과 일치하는지까지 확인한다. SQLite 로 실행하므로 외부 인프라가 필요 없다.
"""

import importlib

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS

_EXPECTED_TABLES = {
    "user_access_logs",
    "users",
    "blog_posts",
    "replies",
    "sns_posts",
    # ORM/Raw 예제가 소유하는 테이블 (Phase 5)
    "catalog_products",
    "sales_orders",
}


def _upgrade_to_head(tmp_path, monkeypatch) -> sa.Engine:
    """빈 SQLite DB를 만들고 마이그레이션을 head 까지 적용한다."""
    import config as config_module

    url = f"sqlite:///{(tmp_path / 'chain.db').as_posix()}"
    # env.py 는 실행 시점의 ``config.db_settings`` 를 읽는다. 그래서 import 시점에 잡아 둔
    # 객체가 아니라 **호출 시점의** 모듈 속성을 patch 한다 — 다른 테스트가
    # ``importlib.reload(config)`` 로 객체를 바꿔 두었으면 import 시점 객체 patch 는 조용히
    # 무시되고 alembic 이 ``.env`` 의 DB 로 간다.
    monkeypatch.setattr(config_module.db_settings, "ALEMBIC_DATABASE_URL", url)

    command.upgrade(Config("alembic.ini"), "head")
    return sa.create_engine(url)


def test_upgrade_head_succeeds_on_empty_database(tmp_path, monkeypatch):
    """빈 DB에서 upgrade head 가 성공하고, 모든 도메인 테이블이 생성된다."""
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"마이그레이션이 생성하지 않은 테이블: {sorted(missing)}"


def test_hashed_password_column_is_added_by_its_own_revision(tmp_path, monkeypatch):
    """users.hashed_password 는 후속 리비전이 추가한다.

    baseline 에 미리 넣으면 b2f1a9c0d3e4 리비전이 무의미해진다. 보정 시 실수로
    합쳐넣지 않았는지 확인한다.
    """
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        columns = {c["name"] for c in sa.inspect(engine).get_columns("users")}
    finally:
        engine.dispose()

    assert "hashed_password" in columns


def test_migrated_schema_matches_models(tmp_path, monkeypatch):
    """마이그레이션 결과가 모델 metadata 와 일치한다(드리프트 없음).

    테이블이 생기기만 하고 컬럼이 어긋나면 운영에서 늦게 터진다.
    """
    Apps().populate(INSTALLED_APPS, run_ready=False)
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"


def test_upgrade_follows_the_patch_after_a_config_reload(tmp_path, monkeypatch, restore_config):
    """다른 테스트가 먼저 ``config`` 를 reload 해도 alembic 은 patch 한 SQLite 로 간다.

    reload 로 생긴 새 설정 객체에는 미끼 URL(``decoy.db``)을 심는다. patch 가 import 시점
    객체에 걸리면 env.py 가 새 객체를 읽어 미끼 쪽에 테이블을 만든다 — 실제 ``.env`` 의
    DB 대신 무해한 파일로 실패를 드러낸다.
    """
    decoy = tmp_path / "decoy.db"
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", f"sqlite:///{decoy.as_posix()}")
    importlib.reload(restore_config)

    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert "users" in tables, "patch 한 URL 에 마이그레이션이 적용되지 않았다"
    assert not decoy.exists(), "alembic 이 reload 된 설정 객체의 URL 로 갔다"
