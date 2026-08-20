"""Phase 8 — 문서가 코드와 어긋나지 않는지 자동 검사.

문서는 조용히 낡는다. 특히 이 저장소처럼 "등록 방법" 자체가 제품인 프로젝트에서는,
README 가 옛 절차를 설명하면 사용자가 그대로 따라 하다 막힌다. 사람이 매번 대조하는
대신 세 가지를 기계로 고정한다.

1. 문서에 적힌 import 경로·심볼이 실제로 존재한다.
2. 제거된 결선 방식(중앙 취합 파일, 디렉터리 스캔, 짧은 이름 등록)이 남아 있지 않다.
3. 문서 간 상대 링크가 실제 파일을 가리킨다.
"""

from __future__ import annotations

import ast
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
    # 이 저장소에는 없는 함수다. 문서에 남으면 "이걸 부르면 모델이 모인다"고 믿게 된다.
    "import_all_models",
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


# =============================================================================
# passive-style 정합성 (development-plan §10.1 D)
#
# 이 저장소는 default-style 에서 갈라져 나왔다. 문서가 옛 절차를 그대로 들고 있으면
# 따라 하는 사람이 `main.py` 를 열어 `include_router` 를 찾다가 막힌다 — 실제로
# 남아 있던 문장들이다. 아래 검사가 그 문장의 부활을 막는다.
# =============================================================================

#: 기준 문서 3종. 사용자가 "따라 하는" 경로가 여기 있다.
BASE_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "ARCHITECTURE.md",
    REPO_ROOT / "docs" / "QUICKSTART.md",
]

#: 옛 결선 방식을 "현재 절차"로 안내하는 문장 패턴.
#: 부정문("쌓지도 않습니다")까지 잡으면 오탐이므로, **지시형** 표현만 본다.
STALE_PROCEDURE_PATTERNS = [
    r"`main\.py` *에 *라우터를 *명시 *등록",
    r"`main\.py` *에 *`?include_router`? *(?:를 )?추가",
    r"__init__\.py` *는 *`router` *를 *공개",
]


@pytest.mark.parametrize("path", BASE_DOCS, ids=lambda p: p.name)
def test_base_docs_document_installed_apps_registration(path: Path):
    """기준 문서 3종 모두 신규 앱의 ``INSTALLED_APPS`` 등록 절차를 설명한다."""
    text = _current_text(path)

    assert "INSTALLED_APPS" in text, f"{path.name} 에 INSTALLED_APPS 등록 절차가 없다"
    assert (
        "apps." in text and "Config" in text
    ), f"{path.name} 이 AppConfig 경로 형식을 보여주지 않는다"


@pytest.mark.parametrize("path", BASE_DOCS, ids=lambda p: p.name)
def test_no_stale_registration_procedure(path: Path):
    """`main.py` 직접 router 등록을 **현재 절차**로 안내하지 않는다."""
    text = _current_text(path)
    hits = [pattern for pattern in STALE_PROCEDURE_PATTERNS if re.search(pattern, text)]
    assert not hits, f"{path.name} 이 옛 등록 절차를 안내한다: {hits}"


def test_feature_init_is_documented_as_marker():
    """기능 root ``__init__.py`` 를 Router/Model 재노출 지점으로 설명하지 않는다.

    실제 코드에서 그것은 빈 package marker 다 — 문서만 옛 역할을 들고 있으면
    사용자가 거기에 import 를 써 넣고 순환 import 를 만든다.
    """
    readme = _current_text(REPO_ROOT / "README.md")

    assert "package marker" in readme, "README 가 기능 __init__.py 의 현재 역할을 설명하지 않는다"

    # docstring 에 "import" 라는 단어가 나오는 것은 정상이다. 실제 import **문**만 본다.
    for init_path in sorted((REPO_ROOT / "app" / "features").glob("*/__init__.py")):
        tree = ast.parse(init_path.read_text(encoding="utf-8"))
        imports = [node for node in tree.body if isinstance(node, ast.Import | ast.ImportFrom)]
        assert not imports, (
            f"{init_path.relative_to(REPO_ROOT)} 가 실제로는 import 를 한다 — "
            "문서 설명(가벼운 package marker)과 어긋난다"
        )


def test_migration_and_runtime_share_registry():
    """migration 과 runtime 이 같은 registry 모델 집합을 쓴다고 설명하고, 실제로도 그렇다."""
    readme = _current_text(REPO_ROOT / "README.md")
    assert "App Registry" in readme, "README 가 metadata 수집 주체를 설명하지 않는다"

    env_source = (REPO_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")
    session_source = (REPO_ROOT / "app" / "core" / "db" / "session.py").read_text(encoding="utf-8")
    assert "populate(INSTALLED_APPS" in env_source, "migrations/env.py 가 registry 를 쓰지 않는다"
    assert "populate(INSTALLED_APPS" in session_source, "session.py 가 registry 를 쓰지 않는다"


# =============================================================================
# 문서가 약속하는 환경변수의 실재 (development-plan §10.1 E)
# =============================================================================

#: 환경변수가 아닌 대문자 토큰. 여기 없는 새 토큰이 나오면 검사가 걸린다 — 의도적이다.
NON_ENV_UPPERCASE_TOKENS = {
    "GET",
    "POST",
    "HS256",
    "INFO",
    "INSTALLED_APPS",
}


def _env_example_keys() -> set[str]:
    """``.env.example`` 의 키. 주석 처리된 예시(``# KEY=``)도 실재하는 키다."""
    text = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    return set(re.findall(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=", text, re.MULTILINE))


def test_env_example_keys_are_parsed():
    """파싱이 비면 아래 검사가 헛통과한다."""
    assert len(_env_example_keys()) >= 20


@pytest.mark.parametrize("path", BASE_DOCS, ids=lambda p: p.name)
def test_documented_env_vars_exist(path: Path):
    """문서가 안내하는 환경변수가 실제로 설정에 존재한다.

    없는 변수를 안내하면 사용자는 그것을 `.env` 에 써 넣고 **아무 일도 일어나지 않는**
    상태를 디버깅하게 된다. 조용히 무시되는 설정이 가장 찾기 어렵다.
    """
    known = _env_example_keys() | NON_ENV_UPPERCASE_TOKENS
    text = _current_text(path)

    unknown = {
        token
        for token in re.findall(r"`([A-Z][A-Z0-9_]{2,})(?:=[^`]*)?`", text)
        if token not in known
    }
    assert not unknown, f"{path.name} 이 존재하지 않는 환경변수를 안내한다: {sorted(unknown)}"
