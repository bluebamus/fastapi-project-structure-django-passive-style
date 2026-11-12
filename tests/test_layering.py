"""패키지 의존 방향 — ``features → core → utils`` (docs/ARCHITECTURE.md §4).

문장으로만 두면 리뷰에서 놓친다. AST 로 실제 import 를 읽어 규칙으로 만든다.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"

#: 문서화된 유일한 교차 기능 의존. auth 는 횡단 관심사라 user 의 모델·리포지토리를 쓴다.
ALLOWED_CROSS_FEATURE_IMPORTS = {("auth", "user")}


def _imported_modules(path: Path) -> list[str]:
    """파일이 import 하는 절대 모듈 경로. 상대 import 는 같은 패키지 안이라 대상이 아니다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.append(node.module)
    return modules


def _source_files() -> list[Path]:
    return [p for p in APP_ROOT.rglob("*.py") if "__pycache__" not in p.parts]


def _violations(package: str, forbidden: tuple[str, ...]) -> list[str]:
    return [
        f"{path.relative_to(REPO_ROOT)} → {module}"
        for path in _source_files()
        if path.relative_to(APP_ROOT).parts[0] == package
        for module in _imported_modules(path)
        if module.startswith(forbidden)
    ]


def test_source_files_are_found():
    """대상이 비면 아래 검사가 헛통과한다."""
    assert len(_source_files()) >= 50


def test_utils_does_not_depend_on_upper_layers():
    """``app/utils`` 는 순수 유틸리티다 — core·features 를 알면 순환이 시작된다."""
    violations = _violations("utils", ("app.core", "app.features"))
    assert not violations, f"utils 가 상위 계층을 import 한다: {violations}"


def test_core_does_not_depend_on_features():
    """``app/core`` 는 인프라다 — 기능은 직접 import 가 아니라 등록 훅으로 연결한다."""
    violations = _violations("core", ("app.features",))
    assert not violations, f"core 가 features 를 import 한다: {violations}"


def test_celery_does_not_depend_on_features():
    """``app/celery`` 는 기능을 모른다 — 워커는 ``INSTALLED_APPS`` 로 기능의 ``tasks`` 를 찾는다.

    중앙 파일이 기능을 import 하면 ``INSTALLED_APPS`` 에서 앱을 빼도 워커가 계속 끌어온다.
    """
    violations = _violations("celery", ("app.features",))
    assert not violations, f"celery 가 features 를 import 한다: {violations}"


def test_features_do_not_import_each_other():
    """기능 간 직접 의존은 문서화된 예외만 허용한다."""
    violations: list[str] = []
    for path in _source_files():
        parts = path.relative_to(APP_ROOT).parts
        if parts[0] != "features" or len(parts) < 2:
            continue
        owner = parts[1]
        for module in _imported_modules(path):
            if not module.startswith("app.features."):
                continue
            other = module.split(".")[2]
            if other == owner or (owner, other) in ALLOWED_CROSS_FEATURE_IMPORTS:
                continue
            violations.append(f"{path.relative_to(REPO_ROOT)} → {module}")

    assert not violations, (
        f"문서화되지 않은 교차 기능 의존: {violations} — "
        "허용하려면 docs/ARCHITECTURE.md §4 와 ALLOWED_CROSS_FEATURE_IMPORTS 를 함께 고치세요"
    )
