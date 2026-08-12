"""마이그레이션 체인이 빈 DB에서 끝까지 적용되는지 검증 (REQ-019/B).

baseline 이 ``user_access_logs`` 하나만 만들고 나머지 도메인 테이블(``users`` ·
``blog_posts`` · ``replies`` · ``sns_posts``)을 통째로 빠뜨리고 있었다. 빈 DB 에
``alembic upgrade head`` 를 돌리면 테이블 1개만 생겨서 blog/reply/sns/user
엔드포인트가 전부 죽는다 — 즉 **신규 클론이 동작하지 않는 상태**였다.

이 결함은 테스트 스위트에 잡히지 않았다. 하니스가 마이그레이션이 아니라
``create_all()`` 로 스키마를 만들기 때문에, 마이그레이션이 비어 있어도 전부 green
이었다. 운영(DEBUG=false)에서는 Alembic 이 유일한 스키마 경로이므로 배포 불가였다.

같은 사고가 다시 나지 않도록, 실제로 빈 DB에 ``upgrade head`` 를 돌려 결과 스키마가
모델과 일치하는지까지 확인한다. SQLite 로 실행하므로 외부 인프라가 필요 없다.
"""

import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.db.session import Base
from app.core.registry import AppRegistry
from config import db_settings

_EXPECTED_TABLES = {
    "user_access_logs",
    "users",
    "blog_posts",
    "replies",
    "sns_posts",
}


def _load_models() -> None:
    """env.py 와 같은 방식으로 Base.metadata 를 채운다(INSTALLED_APPS + 컨벤션 결선).

    탐지 경로를 env.py 와 일치시켜야, 마이그레이션이 보는 모델 집합과 테스트가
    보는 집합이 갈라지지 않는다.
    """
    registry = AppRegistry()
    registry.discover()
    registry.import_models()


def _upgrade_to_head(tmp_path, monkeypatch) -> sa.Engine:
    """빈 SQLite DB를 만들고 마이그레이션을 head 까지 적용한다."""
    url = f"sqlite:///{(tmp_path / 'chain.db').as_posix()}"
    # env.py 는 db_settings.ALEMBIC_URL 을 읽고, 그 프로퍼티가 이 필드를 우선한다.
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", url)

    command.upgrade(Config("alembic.ini"), "head")
    return sa.create_engine(url)


def test_expected_tables_is_not_vacuous() -> None:
    """기대 목록이 모델과 어긋나면 아래 검사들이 헛통과한다."""
    _load_models()
    assert _EXPECTED_TABLES <= set(
        Base.metadata.tables
    ), "기대 테이블이 모델에 없습니다 — 목록이 낡았거나 자동발견이 동작하지 않습니다"


def test_upgrade_head_succeeds_on_empty_database(tmp_path, monkeypatch) -> None:
    """빈 DB에서 upgrade head 가 성공하고, 모든 도메인 테이블이 생성된다."""
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        tables = set(sa.inspect(engine).get_table_names())
    finally:
        engine.dispose()

    missing = _EXPECTED_TABLES - tables
    assert not missing, f"마이그레이션이 생성하지 않은 테이블: {sorted(missing)}"


def test_migrated_schema_matches_models(tmp_path, monkeypatch) -> None:
    """마이그레이션 결과가 모델 metadata 와 일치한다(드리프트 없음).

    테이블이 생기기만 하고 컬럼이 어긋나면 운영에서 늦게 터진다.
    """
    _load_models()
    engine = _upgrade_to_head(tmp_path, monkeypatch)
    try:
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()

    assert diff == [], f"마이그레이션 결과와 모델이 다르다: {diff}"


def test_downgrade_to_base_then_upgrade_again(tmp_path, monkeypatch) -> None:
    """upgrade → downgrade base → 재-upgrade 가 같은 스키마로 돌아온다.

    downgrade 를 아무도 실행해보지 않으면 롤백 경로는 "있다고 믿는 것" 일 뿐이다.
    운영 사고 중에 처음 돌려보다 실패하면 앞으로도 뒤로도 못 간다. baseline 을
    고칠 때 downgrade 쪽 drop 을 빠뜨리는 실수도 여기서 잡힌다.
    """
    cfg = Config("alembic.ini")
    url = f"sqlite:///{(tmp_path / 'roundtrip.db').as_posix()}"
    monkeypatch.setattr(db_settings, "ALEMBIC_DATABASE_URL", url)

    command.upgrade(cfg, "head")
    engine = sa.create_engine(url)
    try:
        before = set(sa.inspect(engine).get_table_names())

        command.downgrade(cfg, "base")
        after_downgrade = set(sa.inspect(engine).get_table_names())
        assert not (
            _EXPECTED_TABLES & after_downgrade
        ), f"downgrade 후에도 남은 테이블: {sorted(_EXPECTED_TABLES & after_downgrade)}"

        command.upgrade(cfg, "head")
        assert set(sa.inspect(engine).get_table_names()) == before
    finally:
        engine.dispose()
