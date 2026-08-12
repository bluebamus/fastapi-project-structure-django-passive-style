"""AC-06·AC-09 — 런타임과 Alembic 이 **같은 registry** 로 model 을 모은다 (FR-06).

예전에는 `app/features/*` 디렉터리를 훑어 `models/models.py` 가 있으면 등록했다.
그러면 등록하지 않은 앱(실험용 디렉터리, 다른 브랜치의 잔재)의 테이블이
`Base.metadata` 에 섞여 autogenerate 와 `create_db_tables()` 에 새어 든다.

수집 대상은 이제 `config.INSTALLED_APPS` 하나다. 여기서는 그 결과가
(1) 실제로 metadata 를 채우고, (2) 등록 앱의 테이블 **만** 담고,
(3) migration 경로와 runtime 경로가 동일한 집합을 보는지를 고정한다.
"""

from app.core.apps import Apps
from app.core.db.session import Base
from config import INSTALLED_APPS


def _registry() -> Apps:
    """migration 과 같은 방식으로 채운 격리 registry."""
    registry = Apps()
    registry.populate(INSTALLED_APPS, run_ready=False)
    return registry


def test_installed_apps_populate_metadata():
    """등록 앱의 models import 가 ``Base.metadata`` 를 채운다."""
    _registry()

    tables = Base.metadata.tables
    assert "user_access_logs" in tables
    assert len(tables) >= 5


def test_metadata_contains_only_installed_app_tables():
    """SEC-02: 등록하지 않은 앱의 테이블은 metadata 에 없다."""
    registry = _registry()

    collected = {model.__tablename__ for model in registry.get_models()}
    assert collected == set(Base.metadata.tables), (
        "Base.metadata 에 등록 앱 소속이 아닌 테이블이 있다: "
        f"{set(Base.metadata.tables) - collected}"
    )


def test_app_without_models_is_not_an_error():
    """모델이 없는 앱(auth)은 정상이며 수집에서 조용히 빠진다."""
    registry = _registry()

    assert registry.get_app_config("auth").get_models() == []
    assert registry.is_installed("app.features.auth") is True


def test_runtime_and_migration_collect_the_same_models():
    """AC-09: 두 경로가 서로 다른 import 경로를 갖지 않는다."""
    from_migration = {model.__tablename__ for model in _registry().get_models()}

    runtime = Apps()
    runtime.populate(INSTALLED_APPS)
    from_runtime = {model.__tablename__ for model in runtime.get_models()}

    assert from_migration == from_runtime
