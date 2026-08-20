"""실제 ``config.INSTALLED_APPS`` 가 registry 계약을 만족하는지 (FR-01·FR-08·SEC-05).

앞의 파일들이 fixture 로 registry **자체** 를 검증했다면, 여기서는 이 프로젝트의
실제 앱 6개가 그 계약 위에서 실제로 조립되는지를 본다. fixture 는 통과하는데 실제
앱은 안 되는 상황(예: ``apps.py`` 오타, label 충돌)을 잡는 자리다.
"""

import ast
from pathlib import Path

import pytest

from app.core.apps import AppConfig, Apps
from app.core.apps.exceptions import AppLookupError
from config import INSTALLED_APPS

EXPECTED_LABELS = ["home", "blog", "reply", "sns", "user", "auth", "catalog", "reports"]
FEATURES_DIR = Path(__file__).resolve().parents[3] / "app" / "features"


@pytest.fixture
def installed() -> Apps:
    registry = Apps()
    registry.populate(INSTALLED_APPS)
    return registry


def test_installed_apps_are_explicit_config_class_paths():
    """§6.1: 짧은 이름 축약은 공개 계약에서 제거했다."""
    assert INSTALLED_APPS
    for entry in INSTALLED_APPS:
        assert entry.startswith("app.features."), entry
        assert entry.endswith("Config"), entry


def test_registry_populates_every_installed_app(installed: Apps):
    """등록 순서대로 label 이 나온다."""
    assert [config.label for config in installed.get_app_configs()] == EXPECTED_LABELS


def test_every_app_has_an_apps_module():
    """FR-01: 모든 기본 앱이 자기 ``apps.py`` 를 갖는다."""
    packages = sorted(p.name for p in FEATURES_DIR.iterdir() if (p / "__init__.py").is_file())
    for name in packages:
        assert (FEATURES_DIR / name / "apps.py").is_file(), f"{name} 에 apps.py 가 없다"


def test_auth_app_has_no_models(installed: Apps):
    """모델이 없는 앱도 정상 설치된다."""
    assert installed.get_app_config("auth").get_models() == []


def test_model_lookup_works_for_real_apps(installed: Apps):
    """FR-05: 실제 model 을 label + 이름으로 찾는다."""
    assert installed.get_model("user", "user").__tablename__ == "users"
    assert installed.get_model("blog", "Post").__tablename__ == "blog_posts"
    with pytest.raises(AppLookupError):
        installed.get_model("auth", "User")


def test_home_ready_registers_access_log_sink():
    """FR-08: sink 등록이 import 부수효과가 아니라 ``ready()`` hook 이다."""
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


def test_ready_hooks_perform_no_io():
    """SEC-05: ``ready()`` 본문에 DB·network·subprocess 호출이 없다.

    구현을 읽어 판정한다 — 실행으로는 "이번엔 안 했다" 만 알 수 있고 "절대 안 한다"
    는 알 수 없기 때문이다. hook 은 프로세스 로컬 결선만 해야 한다.
    """
    banned = {
        "execute",
        "commit",
        "connect",
        "get",
        "post",
        "request",
        "urlopen",
        "run",
        "Popen",
        "check_output",
        "system",
    }

    offenders: list[str] = []
    for apps_py in sorted(FEATURES_DIR.glob("*/apps.py")):
        tree = ast.parse(apps_py.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.FunctionDef) and node.name == "ready"):
                continue
            for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
                func = call.func
                name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                if name in banned:
                    offenders.append(f"{apps_py.parent.name}/apps.py: {name}()")

    assert not offenders, f"ready() 에서 금지된 I/O 를 호출한다: {offenders}"


def test_ready_is_called_once_per_app_on_repeated_populate():
    """CR-07: 같은 registry 를 두 번 populate 해도 hook 은 앱당 한 번이다."""
    calls: list[str] = []

    class Counting(Apps):
        def _run_ready(self) -> None:
            calls.extend(config.label for config in self.app_configs.values())
            super()._run_ready()

    registry = Counting()
    registry.populate(INSTALLED_APPS)
    registry.populate(INSTALLED_APPS)

    assert calls == EXPECTED_LABELS
