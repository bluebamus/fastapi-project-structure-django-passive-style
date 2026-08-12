from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# autogenerate 가 볼 테이블 집합은 런타임과 **같은 registry** 로 정한다 —
# config.INSTALLED_APPS 에 등록된 앱의 models 만 import 한다. 디렉터리 스캔이 아니므로
# 등록하지 않은 앱의 테이블이 마이그레이션에 새어 들어오지 않는다(FR-06·SEC-02).
#
# ``run_ready=False`` 로 3단계 hook 은 건너뛴다. migration 은 스키마만 다뤄야 하고,
# 앱의 runtime 결선(access-log sink 등록 등)을 실행할 이유가 없다(§6.7).
# 전역 registry 대신 격리 인스턴스를 쓰는 이유도 같다 — alembic 프로세스가 애플리케이션
# 전역 상태를 만들지 않는다.
# ---------------------------------------------------------------------------
from app.core.apps import Apps  # noqa: E402
from app.core.db.session import Base  # noqa: E402
from config import INSTALLED_APPS, db_settings  # noqa: E402

Apps().populate(INSTALLED_APPS, run_ready=False)

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Resolve the database URL.
# 환경변수를 직접 읽지 않는다 — 설정은 config.py 가 단독으로 로드한다.
# db_settings.ALEMBIC_URL 이 ALEMBIC_DATABASE_URL 오버라이드(로컬/CI 의 SQLite 등)와
# primary DSN 의 동기 드라이버 치환(aiomysql → pymysql)을 모두 처리한다.
# ---------------------------------------------------------------------------
config.set_main_option("sqlalchemy.url", db_settings.ALEMBIC_URL)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
