"""시각 정책 — UTC·마이크로초 저장 (service-hardening 단계 D · ADR-010 · C-9).

``UTCDateTime`` 의 bind/result 규칙, SQLite 왕복, 모델 기본값, Alembic 렌더 훅, 시각
생성의 단일 출처(``TimezoneSettings.utc_now``)를 고정한다. MySQL 방언(``DATETIME(6)``)
왕복은 ``tests/integration/test_mysql_time_policy.py`` 가 본다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sqlalchemy as sa
from alembic.autogenerate import produce_migrations, render_python_code
from alembic.migration import MigrationContext
from sqlalchemy.dialects import mysql, sqlite
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.models.types import UTCDateTime, render_item
from config import TimezoneSettings

KST = ZoneInfo("Asia/Seoul")


# =============================================================================
# TypeDecorator 규칙
# =============================================================================
def test_aware_kst_is_bound_as_naive_utc():
    bound = UTCDateTime().process_bind_param(
        datetime(2026, 1, 2, 0, 30, 0, 123456, tzinfo=KST), sqlite.dialect()
    )

    assert bound == datetime(2026, 1, 1, 15, 30, 0, 123456)
    assert bound is not None and bound.tzinfo is None


def test_naive_datetime_is_rejected_at_bind():
    """어느 시간대의 벽시계인지 모르는 값은 저장하지 않는다 — 조용한 오해를 막는다."""
    with pytest.raises(ValueError, match="naive"):
        UTCDateTime().process_bind_param(datetime(2026, 1, 2, 0, 30), sqlite.dialect())


def test_result_gets_utc_attached():
    loaded = UTCDateTime().process_result_value(
        datetime(2026, 1, 1, 15, 30, 0, 123456), sqlite.dialect()
    )

    assert loaded == datetime(2026, 1, 1, 15, 30, 0, 123456, tzinfo=UTC)
    assert loaded is not None and loaded.tzinfo is UTC


def test_none_passes_through_both_ways():
    assert UTCDateTime().process_bind_param(None, sqlite.dialect()) is None
    assert UTCDateTime().process_result_value(None, sqlite.dialect()) is None


def test_mysql_column_is_datetime_with_microseconds():
    """MySQL 은 ``DATETIME(6)`` — fsp 0 이면 마이크로초가 잘린다(F-017)."""
    assert sa.Column("t", UTCDateTime()).type.compile(dialect=mysql.dialect()) == "DATETIME(6)"
    assert sa.Column("t", UTCDateTime()).type.compile(dialect=sqlite.dialect()) == "DATETIME"


def test_every_model_datetime_column_uses_utc_datetime():
    """``Mapped[datetime]`` 과 명시 컬럼(reports ``ordered_at`` 포함)이 모두 ``UTCDateTime`` 이다."""
    from app.core.apps import Apps
    from app.core.db.session import Base
    from config import INSTALLED_APPS

    Apps().populate(INSTALLED_APPS, run_ready=False)
    columns = {
        f"{table.name}.{column.name}": column.type
        for table in Base.metadata.sorted_tables
        for column in table.columns
    }
    datetime_columns = [
        name for name, type_ in columns.items() if isinstance(type_, sa.DateTime | UTCDateTime)
    ]
    wrong = [name for name in datetime_columns if not isinstance(columns[name], UTCDateTime)]

    assert "sales_orders.ordered_at" in datetime_columns
    assert len(datetime_columns) == 14, datetime_columns
    assert not wrong, f"UTCDateTime 이 아닌 시각 컬럼: {wrong}"


# =============================================================================
# SQLite 왕복 · 모델 기본값
# =============================================================================
_probe = sa.Table(
    "utc_probe",
    sa.MetaData(),
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("at", UTCDateTime(), nullable=True),
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(_probe.metadata.create_all)
    yield engine
    await engine.dispose()


async def test_sqlite_round_trip_keeps_microseconds_and_returns_aware_utc(engine):
    written = datetime(2026, 1, 2, 0, 30, 0, 654321, tzinfo=KST)
    async with engine.begin() as connection:
        await connection.execute(_probe.insert().values(id=1, at=written))
        await connection.execute(_probe.insert().values(id=2, at=None))
        stored = (
            await connection.execute(sa.text("SELECT at FROM utc_probe WHERE id = 1"))
        ).scalar_one()
        loaded = (await connection.execute(sa.select(_probe.c.at).order_by(_probe.c.id))).all()

    # DB 에는 UTC 벽시계가 들어간다.
    assert stored == "2026-01-01 15:30:00.654321"
    assert loaded[0].at == written
    assert loaded[0].at.tzinfo is UTC
    assert loaded[0].at.microsecond == 654321
    assert loaded[1].at is None


async def test_naive_value_never_reaches_the_database(engine):
    async with engine.begin() as connection:
        with pytest.raises(StatementError, match="naive"):
            await connection.execute(_probe.insert().values(id=1, at=datetime(2026, 1, 2)))


async def test_model_default_timestamps_are_aware_utc():
    from app.core.db.session import Base
    from app.features.blog.models.models import Post

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=[Post.__table__])
        maker = async_sessionmaker(engine, expire_on_commit=True)
        before = datetime.now(UTC)
        async with maker() as session:
            post = Post(title="t", content="c")
            session.add(post)
            await session.commit()
            await session.refresh(post)  # DB 에서 다시 읽은 값으로 본다
        after = datetime.now(UTC)
    finally:
        await engine.dispose()

    for value in (post.created_at, post.updated_at):
        assert value.tzinfo is UTC
        assert before <= value <= after


# =============================================================================
# 시각 생성의 단일 출처
# =============================================================================
def test_utc_now_is_aware_utc_and_now_stays_local():
    settings = TimezoneSettings(TIME_ZONE="Asia/Seoul")

    assert settings.utc_now().utcoffset() == timedelta(0)
    assert settings.now().utcoffset() == timedelta(hours=9)


def test_local_midnight_is_converted_to_a_utc_instant():
    settings = TimezoneSettings(TIME_ZONE="Asia/Seoul")

    assert settings.local_midnight_utc(date(2026, 1, 2)) == datetime(2026, 1, 1, 15, 0, tzinfo=UTC)
    assert settings.local_midnight_utc(date(2026, 1, 2)).tzinfo is UTC


# =============================================================================
# Alembic autogenerate 렌더
# =============================================================================
def test_autogenerate_renders_a_self_contained_type():
    """새 migration 이 앱 모듈을 import 하지 않고 DB 의 실제 모양을 적는다."""
    metadata = sa.MetaData()
    sa.Table(
        "t", metadata, sa.Column("id", sa.Integer, primary_key=True), sa.Column("at", UTCDateTime())
    )
    engine = sa.create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            operations = produce_migrations(context, metadata)
    finally:
        engine.dispose()

    code = render_python_code(operations.upgrade_ops, render_item=render_item)

    assert "sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql')" in code
    assert "app.core" not in code


def test_render_hook_adds_the_dialect_import_and_leaves_other_items_alone():
    class _Context:
        imports: set[str] = set()

    context = _Context()

    assert render_item("type", UTCDateTime(), context) is not False
    assert "from sqlalchemy.dialects import mysql" in context.imports
    assert render_item("type", sa.String(10), context) is False
    assert render_item("column", UTCDateTime(), context) is False
