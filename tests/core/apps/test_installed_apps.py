"""실제 ``config.INSTALLED_APPS`` 가 registry 계약을 만족하는지.

fixture 로 registry 자체를 검증한 다른 파일과 달리, 여기서는 이 프로젝트의 실제 앱이 조립되고
metadata 에 등록 앱의 테이블**만** 담기며 migration 과 runtime 이 같은 모델 집합을 보는지 확인한다.
"""

import pytest

from app.core.apps import AppConfig, Apps
from app.core.apps.exceptions import AppLookupError
from app.core.db.session import Base
from config import INSTALLED_APPS

EXPECTED_LABELS = ["home", "blog", "reply", "sns", "user", "auth", "catalog", "reports"]


@pytest.fixture
def installed() -> Apps:
    registry = Apps()
    registry.populate(INSTALLED_APPS)
    return registry


def test_registry_populates_every_installed_app(installed: Apps):
    """등록 순서대로 label 이 나온다."""
    assert [config.label for config in installed.get_app_configs()] == EXPECTED_LABELS


def test_auth_app_has_no_models(installed: Apps):
    """모델이 없는 앱도 정상 설치된다."""
    assert installed.get_app_config("auth").get_models() == []


def test_model_lookup_works_for_real_apps(installed: Apps):
    """실제 model 을 label + 이름으로 찾는다."""
    assert installed.get_model("user", "user").__tablename__ == "users"
    assert installed.get_model("blog", "Post").__tablename__ == "blog_posts"
    with pytest.raises(AppLookupError):
        installed.get_model("auth", "User")


def test_home_ready_registers_access_log_sink():
    """sink 등록이 import 부수효과가 아니라 ``ready()`` hook 이다."""
    from app.core.middlewares.access_log_sink import (
        get_access_log_sink,
        set_access_log_sink,
    )
    from app.features.home.access_log_sink import HomeAccessLogSink

    original = get_access_log_sink()
    try:
        set_access_log_sink(None)
        config = AppConfig.create("app.features.home.apps.HomeConfig")
        config.ready()
        assert isinstance(get_access_log_sink(), HomeAccessLogSink)
    finally:
        set_access_log_sink(original)


def test_ready_is_called_once_per_app_on_repeated_populate():
    """같은 registry 를 두 번 populate 해도 hook 은 앱당 한 번이다."""
    calls: list[str] = []

    class Counting(Apps):
        def _run_ready(self) -> None:
            calls.extend(config.label for config in self.app_configs.values())
            super()._run_ready()

    registry = Counting()
    registry.populate(INSTALLED_APPS)
    registry.populate(INSTALLED_APPS)

    assert calls == EXPECTED_LABELS


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
    """등록하지 않은 앱의 테이블은 metadata 에 없다."""
    registry = _registry()

    collected = {model.__tablename__ for model in registry.get_models()}
    assert collected == set(Base.metadata.tables), (
        "Base.metadata 에 등록 앱 소속이 아닌 테이블이 있다: "
        f"{set(Base.metadata.tables) - collected}"
    )


def test_runtime_and_migration_collect_the_same_models():
    """두 경로가 서로 다른 import 경로를 갖지 않는다."""
    from_migration = {model.__tablename__ for model in _registry().get_models()}

    runtime = Apps()
    runtime.populate(INSTALLED_APPS)
    from_runtime = {model.__tablename__ for model in runtime.get_models()}

    assert from_migration == from_runtime
