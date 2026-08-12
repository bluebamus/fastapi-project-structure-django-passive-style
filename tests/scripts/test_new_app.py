"""AC-10·AC-11 — 앱 생성기 (FR-09·FR-10·SEC-03·SEC-04).

두 가지를 검증한다.

* **생성 결과가 실제로 동작하는가** — 만든 앱을 registry 에 넣으면 route 가 뜨고,
  넣지 않으면 안 뜬다. 생성기가 설정을 몰래 고치지 않는다는 것도 여기서 본다.
* **생성기가 파일 시스템에 대해 안전한가** — 경로 이탈 입력을 거부하고, 실패했을 때
  대상 디렉터리에 잔해를 남기지 않는다.

두 번째가 특히 중요하다. 생성기는 임의 문자열을 받아 디렉터리를 만드는 코드라, 검사
없이는 ``../../`` 하나로 저장소 밖에 파일을 쓸 수 있다.
"""

from __future__ import annotations

import subprocess  # noqa: S404 - CLI 계약을 실제 실행으로 확인한다
import sys
from pathlib import Path

import pytest

from scripts.new_app import (
    AppScaffoldError,
    build_files,
    config_entry,
    create_app_scaffold,
    next_steps,
    resolve_target,
    validate_name,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def features(tmp_path: Path) -> Path:
    """격리된 가짜 ``app/features`` 디렉터리."""
    root = tmp_path / "features"
    root.mkdir()
    return root


def _snapshot(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*")}


# =============================================================================
# AC-10 — 생성 결과
# =============================================================================
def test_scaffold_creates_apps_module_and_config_class(features: Path):
    """FR-09: ``apps.py`` 와 ``<PascalName>Config`` 를 만든다."""
    target = create_app_scaffold("orders", features_dir=features)

    apps_py = (target / "apps.py").read_text(encoding="utf-8")
    assert "class OrdersConfig(AppConfig):" in apps_py
    assert 'name = "app.features.orders"' in apps_py
    assert (target / "api/routers/router.py").is_file()
    assert "orders_router = APIRouter()" in (target / "api/routers/router.py").read_text(
        encoding="utf-8"
    )


def test_multiword_name_produces_pascal_config():
    """snake_case 이름이 올바른 PascalCase config 이름이 된다."""
    files = build_files("order_items", with_models=False, with_admin=False)

    assert "class OrderItemsConfig(AppConfig):" in files["apps.py"]
    assert config_entry("order_items") == ('    "app.features.order_items.apps.OrderItemsConfig",')


def test_models_and_admin_are_optional(features: Path):
    """옵션 없이는 models/admin 을 만들지 않는다."""
    plain = create_app_scaffold("plainapp", features_dir=features)
    assert not (plain / "models").exists()
    assert not (plain / "admin.py").exists()

    full = create_app_scaffold("fullapp", with_admin=True, features_dir=features)
    assert (full / "models/models.py").is_file()
    assert "admin_views" in (full / "admin.py").read_text(encoding="utf-8")


def test_generator_does_not_touch_config(features: Path):
    """FR-10: 설정 파일을 자동 수정하지 않는다."""
    before = (PROJECT_ROOT / "config.py").read_bytes()

    create_app_scaffold("silentapp", features_dir=features)

    assert (PROJECT_ROOT / "config.py").read_bytes() == before


def test_next_steps_prints_the_exact_registration_line():
    """FR-10: 붙여 넣을 config class 경로를 정확히 출력한다."""
    message = next_steps("orders")

    assert config_entry("orders") in message
    assert "INSTALLED_APPS" in message
    assert "아직 **설치되지 않았다.**" in message


def test_generated_output_claims_no_auto_discovery(features: Path):
    """Phase 6 완료 조건: '자동 발견'·'중앙 등록 불필요' 표현이 없어야 한다."""
    target = create_app_scaffold("claimsapp", with_admin=True, features_dir=features)

    banned = ("자동 발견", "자동 등록", "중앙 등록 불필요", "자동으로 활성화")
    for path in target.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for phrase in banned:
            assert phrase not in text, f"{path.name} 에 '{phrase}' 표현이 남아 있다"
    for phrase in banned:
        assert phrase not in next_steps("claimsapp")


def test_generated_app_is_inactive_until_registered():
    """AC-10 end-to-end: 등록 전에는 비활성, 등록 후 활성화된다.

    생성물이 ``app.features.<name>`` 을 절대 경로로 참조하므로 임시 디렉터리에서는
    import 되지 않는다. 그래서 실제 ``app/features/`` 아래에 만들고 끝나면 지운다 —
    "생성했지만 등록하지 않은 앱" 이라는 상태를 실물로 재현하는 유일한 방법이다.
    """
    import shutil
    import sys as _sys

    from fastapi import FastAPI

    from app.core.apps import Apps
    from app.core.apps.wiring import install_routers
    from config import INSTALLED_APPS

    name = "scaffoldprobe"
    entry = f"app.features.{name}.apps.ScaffoldprobeConfig"
    target = PROJECT_ROOT / "app" / "features" / name
    assert not target.exists(), f"{target} 이 이미 있다 — 이전 실행의 잔해를 정리할 것"

    create_app_scaffold(name)
    try:
        # 1) 디렉터리는 있지만 INSTALLED_APPS 에 없다 → 어떤 결선에도 나오지 않는다.
        assert entry not in INSTALLED_APPS
        unregistered = Apps()
        unregistered.populate(list(INSTALLED_APPS))
        app = FastAPI()
        install_routers(app, unregistered)
        assert not any(f"/{name}/" in path for path in app.openapi()["paths"])
        assert f"app.features.{name}" not in _sys.modules

        # 2) 목록에 넣으면 곧바로 활성화된다.
        registered = Apps()
        registered.populate([*INSTALLED_APPS, entry])
        app = FastAPI()
        install_routers(app, registered)
        assert f"/api/v1/{name}/ping" in app.openapi()["paths"]
    finally:
        for module in [n for n in _sys.modules if n.startswith(f"app.features.{name}")]:
            del _sys.modules[module]
        shutil.rmtree(target, ignore_errors=True)


# =============================================================================
# AC-11 — 경로 안전성
# =============================================================================
@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "..",
        "sub/dir",
        "sub\\dir",
        "/absolute",
        "C:/windows",
        "app.features.x",
        "",
        "Orders",
        "class",
        "1st",
    ],
)
def test_dangerous_names_are_rejected(name: str, features: Path):
    """SEC-03: 경로 이탈·비identifier 입력을 거부한다."""
    before = _snapshot(features)

    with pytest.raises(AppScaffoldError):
        create_app_scaffold(name, features_dir=features)

    assert _snapshot(features) == before, "거부된 입력이 파일을 남겼다"


def _link_dir(link: Path, target: Path) -> None:
    """``link`` 를 ``target`` 을 가리키는 디렉터리 링크로 만든다.

    Windows 에서 ``symlink`` 는 권한이 필요하지만 **junction** 은 필요 없다. 둘 다
    resolve 를 우회시키므로 경계 검사 입장에서는 같은 위협이다 — 그래서 폴백을 둔다.
    이 검사를 skip 으로 넘기면 "경로 이탈을 막는다" 는 보장이 개발 PC 설정에 따라
    사라진다.
    """
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (OSError, NotImplementedError):
        pass
    subprocess.run(  # noqa: S603 - 인자가 이 함수 안에서 만들어진 경로뿐이다
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],  # noqa: S607
        capture_output=True,
        check=True,
        timeout=60,
    )


def test_symlink_escape_is_rejected(tmp_path: Path):
    """SEC-03: 링크를 통과한 resolve 결과가 경계를 벗어나면 거부한다."""
    outside = tmp_path / "outside"
    outside.mkdir()
    features = tmp_path / "features"
    features.mkdir()
    _link_dir(features / "orders", outside)

    with pytest.raises(AppScaffoldError):
        create_app_scaffold("orders", features_dir=features)


def test_existing_target_is_not_partially_overwritten(features: Path):
    """SEC-04: 기존 경로가 있으면 아무것도 바꾸지 않고 실패한다."""
    existing = features / "orders"
    existing.mkdir()
    (existing / "keep.py").write_text("SENTINEL = 1\n", encoding="utf-8")
    before = _snapshot(features)

    with pytest.raises(AppScaffoldError, match="이미 존재"):
        create_app_scaffold("orders", features_dir=features)

    assert _snapshot(features) == before
    assert (existing / "keep.py").read_text(encoding="utf-8") == "SENTINEL = 1\n"


def test_failure_midway_leaves_no_partial_app(features: Path, monkeypatch):
    """SEC-04: 생성 도중 실패하면 대상 경로에 잔해가 없다."""
    import scripts.new_app as module

    def boom(*args, **kwargs):
        raise OSError("디스크 가득 참(모의)")

    monkeypatch.setattr(module.shutil, "move", boom)
    before = _snapshot(features)

    with pytest.raises(OSError, match="모의"):
        create_app_scaffold("orders", features_dir=features)

    assert _snapshot(features) == before


def test_resolve_target_stays_inside_features(features: Path):
    resolved = resolve_target("orders", features)

    assert resolved.parent == features.resolve()
    assert validate_name("order_items") == "order_items"


# =============================================================================
# CLI 계약
# =============================================================================
def test_cli_rejects_bad_name_with_nonzero_exit():
    proc = subprocess.run(  # noqa: S603 - 인터프리터·인자가 이 파일에 고정돼 있다
        [sys.executable, "-m", "scripts.new_app", "../escape"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        check=False,
    )

    assert proc.returncode == 2
    assert "오류" in proc.stderr
