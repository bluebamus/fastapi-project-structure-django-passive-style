"""MySQL 8.4 에서 migration 왕복 검증 (RAW-REP-006 · SCN-ORM-001).

`tests/core/test_migration_chain.py` 는 SQLite 로 `upgrade head` 만 확인한다. 그것으로는
두 가지를 못 본다.

1. **downgrade 가 실제로 되는가** — 새 revision 의 `downgrade()` 는 대개 아무도
   실행하지 않는다. 배포를 되돌려야 하는 날에 처음 돌려보게 되는데, 그날은 이미
   장애 중이다.
2. **MySQL 이 그 DDL 을 받는가** — `Numeric(12, 2)`·`DateTime(timezone=True)`·
   `UniqueConstraint` 는 방언마다 결과가 다르다. SQLite 는 타입을 거의 무시한다.

그래서 `alembic_version` 까지 **완전히 빈 스키마**에서 head → base → head 를 돌린다.
빈 스키마에서 시작하지 않으면 왕복이 이전 실행의 잔재를 밟고 통과해버린다.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext

from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS
from tests.integration.conftest import SYNC_URL

pytestmark = pytest.mark.mysql

#: 이번 Phase 가 추가한 두 테이블. 왕복이 이것들을 만들고 지워야 한다.
NEW_TABLES = ("catalog_products", "sales_orders")


@pytest.fixture
def alembic_on_mysql(mysql_empty_schema, monkeypatch):
    """빈 MySQL 스키마를 대상으로 alembic 을 구성한다.

    ``config`` 모듈에서 미리 import 해 둔 ``db_settings`` 를 패치하면 안 된다.
    다른 테스트가 ``importlib.reload(config)`` 를 부르면 모듈 속성이 **새 객체**로
    바뀌는데, migrations/env.py 는 실행 시점에 그 새 객체를 읽는다. 그러면 패치가
    조용히 무시되고 alembic 이 개발 DB 자격증명으로 붙는다 — 실행 순서에 따라
    통과·실패가 갈리는 실패다(실제로 겪었다).

    그래서 **호출 시점의** 모듈 속성을 패치한다.
    """
    import config as config_module

    monkeypatch.setattr(config_module.db_settings, "ALEMBIC_DATABASE_URL", SYNC_URL)
    return Config("alembic.ini")


def _table_names(engine: sa.Engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def test_head_to_base_to_head_round_trip(alembic_on_mysql):
    """head → base → head 가 MySQL 에서 돈다.

    중간의 `base` 에서 테이블이 **하나도 남지 않아야** 한다. downgrade 가 뭔가를
    남기면 다음 upgrade 가 1050(already exists)으로 깨진다 — 그 실패는 배포
    롤백 도중에 나타난다.
    """
    engine = sa.create_engine(SYNC_URL)
    try:
        command.upgrade(alembic_on_mysql, "head")
        after_upgrade = _table_names(engine)
        assert set(NEW_TABLES) <= after_upgrade, f"신규 테이블이 없다: {sorted(after_upgrade)}"

        command.downgrade(alembic_on_mysql, "base")
        after_downgrade = _table_names(engine) - {"alembic_version"}
        assert not after_downgrade, f"downgrade 후 남은 테이블: {sorted(after_downgrade)}"

        command.upgrade(alembic_on_mysql, "head")
        assert _table_names(engine) == after_upgrade, "재적용 결과가 처음과 다르다"
    finally:
        engine.dispose()


def test_new_revisions_have_a_working_downgrade(alembic_on_mysql):
    """새 revision 두 개를 **하나씩** 되돌린다.

    `base` 까지 한 번에 내리면 중간 revision 의 downgrade 가 깨져 있어도 뒤따르는
    drop 에 묻힐 수 있다. 한 단계씩 내려 각각을 실제로 실행한다.
    """
    engine = sa.create_engine(SYNC_URL)
    try:
        command.upgrade(alembic_on_mysql, "head")

        command.downgrade(alembic_on_mysql, "-1")  # sales_orders 제거
        assert "sales_orders" not in _table_names(engine)
        assert "catalog_products" in _table_names(engine), "한 단계가 두 테이블을 지웠다"

        command.downgrade(alembic_on_mysql, "-1")  # catalog_products 제거
        assert "catalog_products" not in _table_names(engine)

        command.upgrade(alembic_on_mysql, "head")
        assert set(NEW_TABLES) <= _table_names(engine)
    finally:
        engine.dispose()


def test_migrated_schema_matches_the_registry_models(alembic_on_mysql):
    """migration 으로 만든 MySQL 스키마와 registry 모델 사이에 drift 가 없다.

    `create_all`(개발)과 migration(운영)이 갈리면 운영에서만 나는 버그가 된다.
    """
    Apps().populate(INSTALLED_APPS, run_ready=False)
    command.upgrade(alembic_on_mysql, "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            diff = compare_metadata(context, Base.metadata)
    finally:
        engine.dispose()

    assert not diff, f"migration 스키마와 모델이 어긋난다: {diff}"


def test_new_tables_keep_their_column_order(alembic_on_mysql):
    """컬럼 배치가 id → 도메인 → created_at → updated_at 이다 (ADR-014).

    Alembic 은 컬럼을 이름으로 비교해 순서 차이를 diff 로 잡지 않는다. 여기서
    보지 않으면 `create_all` 로 만든 개발 DB 와 **아무 경고 없이** 갈린다.
    """
    command.upgrade(alembic_on_mysql, "head")

    expected = {
        "catalog_products": [
            "id",
            "sku",
            "name",
            "description",
            "price",
            "stock",
            "is_active",
            "created_at",
            "updated_at",
        ],
        "sales_orders": [
            "id",
            "order_no",
            "customer",
            "total_amount",
            "status",
            "ordered_at",
            "created_at",
            "updated_at",
        ],
    }

    engine = sa.create_engine(SYNC_URL)
    try:
        inspector = sa.inspect(engine)
        for table, columns in expected.items():
            actual = [column["name"] for column in inspector.get_columns(table)]
            assert actual == columns, f"{table} 컬럼 배치가 다르다: {actual}"
    finally:
        engine.dispose()


def test_money_columns_are_decimal_on_mysql(alembic_on_mysql):
    """금액 컬럼이 MySQL 에서 DECIMAL 로 만들어진다.

    SQLite 는 타입을 거의 무시하므로 단위 테스트로는 확인할 수 없다. DOUBLE 로
    만들어지면 합계가 조용히 틀어진다.
    """
    command.upgrade(alembic_on_mysql, "head")

    engine = sa.create_engine(SYNC_URL)
    try:
        inspector = sa.inspect(engine)
        price = {c["name"]: c for c in inspector.get_columns("catalog_products")}["price"]
        amount = {c["name"]: c for c in inspector.get_columns("sales_orders")}["total_amount"]
    finally:
        engine.dispose()

    for name, column in (("catalog_products.price", price), ("sales_orders.total_amount", amount)):
        assert isinstance(column["type"], sa.Numeric), f"{name} 이 {column['type']} 로 만들어졌다"
        assert column["type"].scale == 2, f"{name} 의 소수 자릿수가 2 가 아니다"
