"""Phase 8 — 문서가 코드와 어긋나지 않는지 자동 검사.

문서는 조용히 낡는다. 특히 이 저장소처럼 "등록 방법" 자체가 제품인 프로젝트에서는,
README 가 옛 절차를 설명하면 사용자가 그대로 따라 하다 막힌다. 사람이 매번 대조하는
대신 세 가지를 기계로 고정한다.

1. 문서에 적힌 import 경로·심볼이 실제로 존재한다.
2. 제거된 결선 방식(중앙 취합 파일, 디렉터리 스캔, 짧은 이름 등록)이 남아 있지 않다.
3. 문서 간 상대 링크가 실제 파일을 가리킨다.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "ARCHITECTURE.md",
    REPO_ROOT / "docs" / "QUICKSTART.md",
    *sorted((REPO_ROOT / "docs" / "django-style-app-registry").glob("*.md")),
]

# 작업 **전** 상태를 기록한 역사 문서 — 옛 결선 방식이 나오는 것이 정상이다.
# 지우거나 덮어쓰지 않고 상태를 명시해 보존한다(문서 세트 인덱스의 변경 관리 규칙 4).
HISTORICAL_DOCS = {
    "DJANGO-STYLE-MANUAL-APP-INTEGRATION-PLAN.md",
    "PRODUCTION-READINESS-DEVELOPMENT-PLAN.md",
}
CURRENT_DOCS = [path for path in DOCS if path.name not in HISTORICAL_DOCS]

# 이 저장소에서 사라진 결선 방식. 문서에 남아 있으면 사용자를 잘못 이끈다.
REMOVED_REFERENCES = [
    "models_registry",
    "app/features/admin.py",
    "app.features.admin",
    "ADMIN_VIEWS",
    "register_admin_views",
    "create_admin_interface",
]

# 문서가 약속하는 공개 심볼 — 실제로 있어야 한다.
PROMISED_SYMBOLS = {
    "app.core.apps": ["AppConfig", "Apps", "apps"],
    "app.core.apps.wiring": ["install_routers", "install_admin", "create_admin"],
    "app.core.bootstrap": ["create_app", "lifespan"],
    "app.core.apps.exceptions": [
        "AppRegistryError",
        "ImproperlyConfigured",
        "AppRegistryNotReady",
        "AppLookupError",
    ],
    "scripts.new_app": ["create_app_scaffold", "next_steps", "config_entry"],
}


def test_documents_exist():
    """대조 대상이 비어 있으면 아래 검사가 헛통과한다."""
    assert len(DOCS) >= 6
    for path in DOCS:
        assert path.is_file(), path


#: 변경 이력 섹션은 과거를 기록하는 자리다 — 옛 이름이 나오는 것이 정상이다.
CHANGELOG_HEADINGS = ("## 8. 변경 이력", "## 10. 개발 내역과 설계의 발전")


def _current_text(path: Path) -> str:
    """변경 이력 섹션을 제외한 본문."""
    text = path.read_text(encoding="utf-8")
    for heading in CHANGELOG_HEADINGS:
        text = text.partition(heading)[0]
    return text


@pytest.mark.parametrize("path", CURRENT_DOCS, ids=lambda p: p.name)
def test_no_removed_wiring_references(path: Path):
    """제거된 결선 방식을 설명하는 문장이 남아 있지 않다."""
    text = _current_text(path)
    found = [token for token in REMOVED_REFERENCES if token in text]
    assert not found, f"{path.name} 에 제거된 결선 방식이 남아 있다: {found}"


@pytest.mark.parametrize("module_name", sorted(PROMISED_SYMBOLS), ids=lambda n: n)
def test_documented_symbols_exist(module_name: str):
    """문서가 언급하는 모듈과 심볼이 실제로 존재한다."""
    module = importlib.import_module(module_name)

    missing = [name for name in PROMISED_SYMBOLS[module_name] if not hasattr(module, name)]
    assert not missing, f"{module_name} 에 없는 이름: {missing}"


@pytest.mark.parametrize("path", DOCS, ids=lambda p: p.name)
def test_relative_links_resolve(path: Path):
    """문서 간 상대 링크가 실제 파일을 가리킨다."""
    text = path.read_text(encoding="utf-8")
    broken: list[str] = []
    for target in re.findall(r"\]\(([^)]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        resolved = (path.parent / target.split("#", 1)[0]).resolve()
        if not resolved.exists():
            broken.append(target)

    assert not broken, f"{path.name} 의 깨진 링크: {broken}"


def test_installed_apps_examples_match_real_entries():
    """문서의 등록 예제가 실제 ``INSTALLED_APPS`` 형식과 같다."""
    from config import INSTALLED_APPS

    architecture = (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    for entry in INSTALLED_APPS:
        assert entry in architecture, f"ARCHITECTURE.md 의 예제에 {entry} 가 없다"


def test_generator_output_matches_documented_line():
    """README 가 안내하는 등록 한 줄이 생성기 출력과 같은 형식이다."""
    from scripts.new_app import config_entry

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert config_entry("orders").strip() in (
        readme + (REPO_ROOT / "docs" / "ARCHITECTURE.md").read_text(encoding="utf-8")
    )
