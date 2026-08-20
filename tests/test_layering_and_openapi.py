"""E 게이트 — 계층 규칙과 OpenAPI 비공허성 (development-plan §10.1 E).

README 의 "의존은 한 방향으로만 흐른다(features → core → utils)" 는 **문장**이었다.
문장은 리뷰에서 놓친다. 여기서 AST 로 실제 import 를 읽어 규칙으로 만든다.

OpenAPI 쪽은 "문서가 있다"가 아니라 "문서가 비어 있지 않다"를 본다 — 스키마 생성이
조용히 실패해 빈 문서를 내보내도 `/docs` 는 200 을 돌려준다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"

#: 문서화된 유일한 교차 기능 의존. auth 는 횡단 관심사라 user 의 식별 모델·리포지토리를 쓴다
#: (README `app/` 구현 규칙 표에 명시). 이 집합이 늘어나면 규칙을 먼저 고쳐야 한다.
ALLOWED_CROSS_FEATURE_IMPORTS = {("auth", "user")}


def _imported_modules(path: Path) -> list[str]:
    """파일이 import 하는 절대 모듈 경로. 상대 import 는 같은 기능 안이라 대상이 아니다."""
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


def test_source_files_are_found():
    """대상이 비면 아래 검사가 헛통과한다."""
    assert len(_source_files()) >= 50


def test_utils_does_not_depend_on_upper_layers():
    """``app/utils`` 는 순수 유틸리티다 — core·features 를 알면 순환이 시작된다."""
    violations = [
        f"{path.relative_to(REPO_ROOT)} → {module}"
        for path in _source_files()
        if path.relative_to(APP_ROOT).parts[0] == "utils"
        for module in _imported_modules(path)
        if module.startswith(("app.core", "app.features"))
    ]
    assert not violations, f"utils 가 상위 계층을 import 한다: {violations}"


def test_core_does_not_depend_on_features():
    """``app/core`` 는 프레임워크 인프라다 — 특정 기능을 알면 재사용이 끝난다.

    기능이 core 에 자신을 연결해야 할 때는 직접 import 가 아니라 등록 훅
    (``access_log_sink.register_sink()``, ``AppConfig.ready()``)을 쓴다.
    """
    violations = [
        f"{path.relative_to(REPO_ROOT)} → {module}"
        for path in _source_files()
        if path.relative_to(APP_ROOT).parts[0] == "core"
        for module in _imported_modules(path)
        if module.startswith("app.features")
    ]
    assert not violations, f"core 가 features 를 import 한다: {violations}"


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
        "허용하려면 README 규칙과 ALLOWED_CROSS_FEATURE_IMPORTS 를 함께 고치세요"
    )


# =============================================================================
# OpenAPI 비공허성
# =============================================================================
@pytest.fixture(scope="module")
def openapi_schema() -> dict:
    from app.core.bootstrap import create_app

    return create_app().openapi()


def test_openapi_is_not_empty(openapi_schema: dict):
    """경로가 하나도 없는 문서는 200 을 주면서도 아무것도 알려주지 않는다."""
    paths = openapi_schema.get("paths", {})
    assert len(paths) >= 5, f"OpenAPI 경로가 {len(paths)}개뿐이다 — 스키마 생성이 깨졌을 수 있다"


def test_openapi_operations_have_responses(openapi_schema: dict):
    """모든 path operation 이 응답 정의를 갖는다."""
    missing: list[str] = []
    for path, operations in openapi_schema["paths"].items():
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not operation.get("responses"):
                missing.append(f"{method.upper()} {path}")

    assert not missing, f"응답 정의가 없는 operation: {missing}"


def test_openapi_operations_are_described(openapi_schema: dict):
    """summary 없는 operation 은 `/docs` 에서 함수 이름만 덩그러니 남는다."""
    undescribed: list[str] = []
    for path, operations in openapi_schema["paths"].items():
        for method, operation in operations.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not (operation.get("summary") or operation.get("description")):
                undescribed.append(f"{method.upper()} {path}")

    assert not undescribed, f"설명이 없는 operation: {undescribed}"


def test_openapi_component_schemas_exist(openapi_schema: dict):
    """응답 모델이 실제 스키마로 풀렸는지 — 비면 DTO 계약이 문서에 없다는 뜻이다."""
    schemas = openapi_schema.get("components", {}).get("schemas", {})
    assert schemas, "components.schemas 가 비었다 — 응답 모델이 문서화되지 않았다"


# =============================================================================
# 검수 게이트 stdio 고정 (C-7)
# =============================================================================
def test_ci_pins_utf8_stdio():
    """CI 가 검수 도구의 stdio 를 UTF-8 로 고정한다.

    한글 리포트를 출력하는 순간 도구가 UnicodeEncodeError 로 죽으면, 게이트는
    "실패를 보고하려다 죽는" 상태가 된다 — 그 크래시 뒤에 진짜 실패가 가려진다.
    """
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "PYTHONIOENCODING: utf-8" in workflow
    assert 'PYTHONUTF8: "1"' in workflow


def test_python_subprocesses_in_tests_force_utf8():
    """테스트가 띄우는 파이썬 자식 프로세스는 ``-X utf8`` 을 붙인다.

    부모는 UTF-8 로 읽는데 자식이 로컬 코드페이지로 쓰면 stderr 디코딩이 터져
    ``proc.stderr`` 가 통째로 사라진다 — 실패 원인이 보이지 않는 상태가 된다.
    """
    offenders: list[str] = []
    for path in (REPO_ROOT / "tests").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            if "sys.executable" in line and '"-X", "utf8"' not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {line.strip()}")

    assert not offenders, f"-X utf8 없이 파이썬 자식 프로세스를 띄운다: {offenders}"
