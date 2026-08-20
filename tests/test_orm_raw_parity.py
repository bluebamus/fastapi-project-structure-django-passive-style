"""ORM 예제와 Raw 예제가 **Repository 만 다르다** (ADR-002 · Phase 5 완료 조건).

개발계획서의 Phase 5 완료 조건은 이렇다 — "사용자는 두 예제를 나란히 비교해 데이터
접근 방식만 교체할 수 있다". 그건 문장으로 두면 다음 커밋에 조용히 무너진다. 누가
`reports` 에만 편의 계층을 하나 얹거나, `catalog` 의 Dependency 를 다르게 만들면
비교가 성립하지 않는데, 그 사실은 아무 테스트도 실패시키지 않는다.

그래서 여기서 **구조를 기계로 대조**한다. 두 기능이 같아야 하는 것과, 달라야 하는
것을 각각 고정한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

ORM_FEATURE = "catalog"
RAW_FEATURE = "reports"

#: 두 예제가 **똑같이** 가져야 하는 파일. 하나라도 빠지면 "나란히 비교"가 깨진다.
SHARED_LAYOUT = (
    "__init__.py",
    "apps.py",
    "admin.py",
    "api/routers/router.py",
    "dependencies/__init__.py",
    "exceptions.py",
    "models/models.py",
    "repositories/__init__.py",
    "schemas/__init__.py",
    "services/__init__.py",
)


def _feature_path(feature: str, relative: str) -> Path:
    return REPO_ROOT / "app" / "features" / feature / relative


def _source(feature: str, relative: str) -> str:
    return _feature_path(feature, relative).read_text(encoding="utf-8")


def _base_classes(feature: str, relative: str, class_name: str) -> list[str]:
    """해당 클래스가 상속하는 base 이름 목록."""
    tree = ast.parse(_source(feature, relative))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [ast.unparse(base) for base in node.bases]
    raise AssertionError(f"{feature}/{relative} 에 {class_name} 가 없다")


# =============================================================================
# 같아야 하는 것
# =============================================================================
@pytest.mark.parametrize("relative", SHARED_LAYOUT)
def test_both_examples_share_the_same_layout(relative: str):
    """두 기능의 디렉터리 구조가 같다."""
    for feature in (ORM_FEATURE, RAW_FEATURE):
        assert _feature_path(feature, relative).exists(), f"{feature} 에 {relative} 가 없다"


@pytest.mark.parametrize("feature", [ORM_FEATURE, RAW_FEATURE])
def test_both_features_are_installed_by_the_registry(feature: str):
    """둘 다 `INSTALLED_APPS` 로만 설치된다 — main.py 는 건드리지 않는다."""
    from config import INSTALLED_APPS

    assert any(f"features.{feature}.apps." in entry for entry in INSTALLED_APPS)


def test_neither_example_is_wired_in_main():
    """main.py 에 예제 이름이 나타나지 않는다 (passive-style 계약)."""
    main_source = (REPO_ROOT / "main.py").read_text(encoding="utf-8")

    for feature in (ORM_FEATURE, RAW_FEATURE):
        assert feature not in main_source, f"main.py 가 {feature} 를 직접 참조한다"


@pytest.mark.parametrize("feature", [ORM_FEATURE, RAW_FEATURE])
def test_both_services_extend_the_same_base(feature: str):
    """Service 계층은 공통이다 — 여기가 갈리면 트랜잭션 규칙도 갈린다."""
    service = {ORM_FEATURE: ("services/catalog_service.py", "CatalogService")}.get(
        feature, ("services/report_service.py", "ReportService")
    )

    assert _base_classes(feature, *service) == ["BaseService"]


@pytest.mark.parametrize("feature", [ORM_FEATURE, RAW_FEATURE])
def test_read_paths_use_the_read_only_session(feature: str):
    """조회는 양쪽 모두 read-only 세션을 쓴다 (C-1·C-17)."""
    dependencies = {
        ORM_FEATURE: "dependencies/catalog_dependencies.py",
        RAW_FEATURE: "dependencies/reports_dependencies.py",
    }[feature]

    assert "get_read_only_db_session" in _source(feature, dependencies)


@pytest.mark.parametrize("feature", [ORM_FEATURE, RAW_FEATURE])
def test_no_feature_commits_outside_the_view(feature: str):
    """Repository 도 Service 도 커밋하지 않는다 (ADR-008).

    ``BaseService.commit`` 정의는 core 에 있고, 기능 코드는 그것을 **호출만** 한다.
    호출은 View 에서 일어나야 한다.
    """
    feature_root = REPO_ROOT / "app" / "features" / feature
    offenders = []
    for path in sorted(feature_root.rglob("*.py")):
        if "/tests/" in path.as_posix() or "api/routers" in path.as_posix():
            continue
        source = path.read_text(encoding="utf-8")
        code = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
        if any(".commit()" in line for line in code):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, f"View 밖에서 커밋한다: {offenders}"


@pytest.mark.parametrize("feature", [ORM_FEATURE, RAW_FEATURE])
def test_views_return_pydantic_dtos(feature: str):
    """양쪽 View 모두 `response_model` 을 선언한다 — 내부 타입이 새지 않는다."""
    view = {
        ORM_FEATURE: "api/routers/v1/products.py",
        RAW_FEATURE: "api/routers/v1/sales_reports.py",
    }[feature]

    assert "response_model=" in _source(feature, view)


# =============================================================================
# 달라야 하는 것 — 이 차이가 예제의 요점이다
# =============================================================================
def test_repositories_extend_different_bases():
    """ORM 은 `BaseRepository`, Raw 는 `RawRepositoryBase` 다 (AR-003)."""
    orm_bases = _base_classes(
        ORM_FEATURE, "repositories/product_repository.py", "ProductRepository"
    )
    raw_bases = _base_classes(
        RAW_FEATURE, "repositories/sales_report_repository.py", "SalesReportRawRepository"
    )

    assert orm_bases == ["BaseRepository[Product]"]
    assert raw_bases == ["RawRepositoryBase"]


def test_only_the_raw_repository_owns_sql():
    """SQL 문자열은 Raw Repository 에만 있다.

    다른 계층으로 새면 "Repository 만 다르다"가 무너진다 — View 나 Service 가 SQL 을
    알기 시작하면 데이터 접근 방식을 바꿀 때 그 계층도 함께 고쳐야 한다.
    """
    for feature in (ORM_FEATURE, RAW_FEATURE):
        feature_root = REPO_ROOT / "app" / "features" / feature
        for path in sorted(feature_root.rglob("*.py")):
            if "/tests/" in path.as_posix():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            has_text_call = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "text"
                for node in ast.walk(tree)
            )
            if not has_text_call:
                continue
            assert (
                path.name == "sales_report_repository.py"
            ), f"{path.relative_to(REPO_ROOT)} 가 SQL 을 소유한다 — Raw Repository 밖이다"


def _uses_from_attributes(feature: str, relative: str) -> bool:
    """``from_attributes`` 를 **코드에서** 설정하는지. 주석·docstring 은 세지 않는다."""
    tree = ast.parse(_source(feature, relative))
    return any(
        isinstance(node, ast.Call)
        and any(keyword.arg == "from_attributes" for keyword in node.keywords)
        for node in ast.walk(tree)
    )


def test_only_the_orm_response_uses_from_attributes():
    """ORM 응답만 `from_attributes` 를 쓴다.

    Raw 결과는 ORM 객체가 아니라 ``RowMapping`` 이라 그 설정에 기댈 수 없다. 기대면
    검증이 조용히 헐거워진다.

    문자열이 아니라 AST 로 본다 — 두 파일 모두 이 설정을 **설명하는** 문장을 담고
    있어서, 문자열 검사는 docstring 에 걸려 헛통과한다.
    """
    assert _uses_from_attributes(ORM_FEATURE, "schemas/product_schema.py")
    assert not _uses_from_attributes(
        RAW_FEATURE, "schemas/report_schema.py"
    ), "Raw DTO 가 ORM 변환 설정을 쓴다"


def test_raw_service_validates_rows_explicitly():
    """Raw Service 가 `dict(row)` 를 명시적으로 검증한다 (RAW-REP-005)."""
    source = _source(RAW_FEATURE, "services/report_service.py")

    assert "model_validate(dict(row))" in source, "RowMapping 을 검증 없이 흘린다"
