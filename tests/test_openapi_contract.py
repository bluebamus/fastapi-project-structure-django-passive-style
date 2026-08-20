"""OpenAPI 스키마 정합성 (DOC-004 · DOC-005).

Scalar 문서는 코드에서 자동으로 나오기 때문에 "잘 나오고 있겠지"라고 믿기 쉽다.
실제로는 조용히 어긋난다 — 태그를 선언만 하고 안 쓰거나, 서로 다른 모듈에 같은
이름의 Pydantic class 를 두면 schema key 가 모듈 경로로 튀어나온다. 둘 다 아무
테스트도 실패시키지 않고, 문서를 열어 보는 사람만 이상하다고 느낀다.

여기서는 **규칙마다 하나씩** 검사한다. 규칙이 뭉쳐 있으면 하나가 깨졌을 때 나머지도
같이 빨간불이 되어 원인을 좁힐 수 없다.

공허한 통과 방지:
    검사 대상이 0개면 모든 규칙이 통과한다. 그건 "문제 없음"이 아니라 "검사 안 함"이다.
    그래서 operation 수·schema 수·예제 DTO 집합을 각각 하한으로 고정한다.
"""

from __future__ import annotations

import collections
from typing import Any

import pytest

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

#: 본문이 없는 성공 응답. 이것만 schema 없이 통과시킨다.
NO_CONTENT = "204"

#: ORM/Raw 예제가 OpenAPI 에 반드시 내보내야 하는 DTO. 예제가 문서에서 사라지면
#: "나란히 비교"가 성립하지 않는다(Phase 5 완료 조건).
REQUIRED_EXAMPLE_SCHEMAS = frozenset(
    {
        # ORM 예제
        "ProductCreate",
        "ProductUpdate",
        "ProductResponse",
        "ProductListResponse",
        # Raw 예제
        "DailySalesItem",
        "DailySalesReportResponse",
    }
)

#: 검사 대상 하한. 실제 값보다 낮게 잡아 라우트 추가 때마다 고치지 않아도 되게 하되,
#: 라우터 등록이 통째로 빠지면(0 이 되면) 즉시 걸리도록 충분히 크게 둔다.
MIN_OPERATIONS = 30
MIN_SCHEMAS = 25


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    from main import app

    return app.openapi()


@pytest.fixture(scope="module")
def operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """(method, path, operation) 목록."""
    return [
        (method, path, operation)
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    ]


@pytest.fixture(scope="module")
def schemas(spec: dict[str, Any]) -> dict[str, Any]:
    return spec.get("components", {}).get("schemas", {})


def _api_routes(router: Any) -> list[Any]:
    """앱에 마운트된 `APIRoute` 를 전부 모은다.

    ``app.routes`` 를 그냥 훑으면 안 된다 — FastAPI 0.141 은 `include_router` 로 붙인
    라우터를 `_IncludedRouter` 로 감싸 두고 하위 라우트를 **평탄화하지 않는다**.
    그대로 순회하면 `/health`·`/ready` 세 개만 보이고, 기능 라우트를 대상으로 하는
    규칙이 전부 조용히 헛돈다(실제로 fail-on-revert 에서 이 상태가 드러났다).
    """
    from fastapi.routing import APIRoute

    found: list[Any] = []
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            found.append(route)
            continue
        inner = getattr(route, "original_router", None) or route
        if inner is not route or hasattr(inner, "routes"):
            found.extend(_api_routes(inner))
    return found


@pytest.fixture(scope="module")
def routes() -> list[Any]:
    """문서에 나오는 라우트만. `/docs` 처럼 스키마에서 빠지는 것은 대상이 아니다."""
    from main import app

    return [route for route in _api_routes(app) if route.include_in_schema]


def test_route_objects_are_reachable(routes, operations):
    """라우트 객체를 operation 수만큼 찾았는지 — 아래 두 규칙의 전제다."""
    assert len(routes) >= len(operations), (
        f"operation {len(operations)}개 중 라우트 객체는 {len(routes)}개만 찾았다 — "
        "라우터 평탄화가 깨졌고, 라우트 기반 규칙이 헛돈다"
    )


# =============================================================================
# 0. 검사가 공허하지 않은가 — 다른 모든 규칙의 전제
# =============================================================================
def test_operation_set_is_not_empty(operations):
    """operation 이 0개면 아래 규칙 전부가 헛통과한다."""
    assert len(operations) >= MIN_OPERATIONS, (
        f"operation 이 {len(operations)}개뿐이다 — 라우터 등록이 빠졌거나 "
        "OpenAPI 생성이 실패했다"
    )


def test_schema_set_is_not_empty(schemas):
    assert len(schemas) >= MIN_SCHEMAS, f"schema 가 {len(schemas)}개뿐이다"


def test_example_dtos_reach_the_documentation(schemas):
    """ORM/Raw 예제 DTO 가 실제로 문서에 나온다 (DOC-005)."""
    missing = sorted(REQUIRED_EXAMPLE_SCHEMAS - set(schemas))

    assert not missing, f"예제 DTO 가 OpenAPI 에 없다: {missing}"


# =============================================================================
# 1. operationId — 클라이언트 생성기가 메서드 이름으로 쓴다
# =============================================================================
def test_every_operation_id_is_authored(routes):
    """operationId 를 **사람이 지정했는지** 본다.

    "비어 있는가"로는 검사가 되지 않는다 — 주지 않으면 FastAPI 가 함수명과 경로를
    이어 붙여(`get_product_api_v1_catalog_products__product_id__get`) 자동으로 채운다.
    그 id 는 **경로를 바꾸면 함께 바뀌고**, 그 순간 이 스키마로 만든 클라이언트의
    메서드 이름이 전부 갈린다. 그래서 자동 생성값과 같은지를 본다.
    """
    from fastapi.routing import generate_unique_id

    generated = [
        f"{sorted(route.methods)} {route.path}"
        for route in routes
        if route.operation_id in (None, generate_unique_id(route))
    ]

    assert not generated, f"operationId 가 자동 생성값이다: {generated}"


def test_operation_ids_are_unique(operations):
    """중복되면 생성기가 메서드 하나를 조용히 덮어쓴다."""
    counts = collections.Counter(op.get("operationId") for _, _, op in operations)
    duplicates = sorted(name for name, count in counts.items() if count > 1)

    assert not duplicates, f"operationId 중복: {duplicates}"


# =============================================================================
# 2. tag metadata — 선언과 사용이 정확히 일치해야 한다 (DOC-004)
# =============================================================================
def _declared_tags() -> list[str]:
    from app.core.tags_metadata import tags_metadata

    return [tag["name"] for tag in tags_metadata]


def _used_tags(operations) -> set[str]:
    return {tag for _, _, op in operations for tag in op.get("tags", [])}


def test_every_used_tag_is_declared(operations):
    """선언하지 않은 태그는 Scalar 에 설명 없이 나타난다."""
    undeclared = sorted(_used_tags(operations) - set(_declared_tags()))

    assert not undeclared, f"metadata 에 없는 태그: {undeclared}"


def test_every_declared_tag_is_used(operations):
    """쓰지 않는 태그는 좌측 목록에 빈 항목으로 남는다."""
    unused = sorted(set(_declared_tags()) - _used_tags(operations))

    assert not unused, f"선언했지만 쓰지 않는 태그: {unused}"


def test_declared_tags_have_no_duplicates():
    declared = _declared_tags()

    assert len(declared) == len(set(declared)), f"태그 중복 선언: {declared}"


def test_every_operation_carries_a_tag(operations):
    """태그가 없으면 Scalar 의 'default' 그룹에 떨어진다."""
    untagged = [f"{m.upper()} {p}" for m, p, op in operations if not op.get("tags")]

    assert not untagged, f"태그 없는 operation: {untagged}"


def test_no_tag_claims_to_be_unimplemented():
    """구현된 기능에 '미구현/예정' 설명이 남아 있지 않다 (DOC-004).

    문서가 "예정"이라고 말하는 기능을 사용자가 이미 호출할 수 있는 상태는, 문서를
    믿지 않게 만든다는 점에서 문서가 없는 것보다 나쁘다.
    """
    from app.core.tags_metadata import tags_metadata

    offenders = [
        tag["name"]
        for tag in tags_metadata
        if "미구현" in tag.get("description", "") or "예정" in tag.get("description", "")
    ]

    assert not offenders, f"구현됐는데 '미구현/예정' 이라고 적힌 태그: {offenders}"


# =============================================================================
# 3. 응답 계약 — 성공 응답에 schema 가 있어야 한다
# =============================================================================
def test_success_responses_declare_a_schema(operations):
    """204 를 뺀 2xx 에는 본문 스키마가 있어야 한다.

    없으면 클라이언트 생성기가 응답 타입을 `any` 로 만든다 — 타입이 있는 언어에서는
    그 순간 계약 검사가 사라진다.
    """
    import json

    missing = []
    for method, path, operation in operations:
        for code, response in operation.get("responses", {}).items():
            if not code.startswith("2") or code == NO_CONTENT:
                continue
            schema = response.get("content", {}).get("application/json", {}).get("schema", {})
            # `content` 유무로는 검사가 안 된다 — `response_model` 을 지워도 FastAPI 는
            # `{"title": "Response Listproducts"}` 같은 **타입 없는** schema 를 넣는다.
            # 이름 있는 컴포넌트를 참조하는지를 본다.
            if "$ref" not in json.dumps(schema):
                missing.append(f"{method.upper()} {path} -> {code}: {json.dumps(schema)[:60]}")

    assert not missing, f"성공 응답이 이름 있는 schema 를 참조하지 않는다: {missing}"


def test_no_content_responses_carry_no_body(operations):
    """204 에 본문을 선언하면 규격 위반이다 — 클라이언트가 파싱을 시도한다."""
    offenders = [
        f"{m.upper()} {p}"
        for m, p, op in operations
        if "content" in op.get("responses", {}).get(NO_CONTENT, {})
    ]

    assert not offenders, f"204 에 본문 schema 가 있다: {offenders}"


def test_documented_error_responses_reference_the_shared_model(operations, spec):
    """오류 응답은 공통 `ErrorResponse` 를 참조한다.

    도메인마다 다른 오류 모양을 내보내면 클라이언트가 상태 코드별로 분기해야 한다.
    """
    offenders = []
    for method, path, operation in operations:
        for code, response in operation.get("responses", {}).items():
            if not (code.startswith("4") or code.startswith("5")):
                continue
            content = response.get("content", {}).get("application/json", {})
            ref = content.get("schema", {}).get("$ref", "")
            # FastAPI 가 기본 제공하는 422(HTTPValidationError)는 대상이 아니다.
            if not ref or ref.endswith("/HTTPValidationError"):
                continue
            if not ref.endswith("/ErrorResponse"):
                offenders.append(f"{method.upper()} {path} -> {code}: {ref}")

    assert not offenders, f"공통 오류 모델을 쓰지 않는 응답: {offenders}"


# =============================================================================
# 4. 문서 품질 — Scalar 에서 읽을 수 있는 형태인가
# =============================================================================
def test_every_operation_has_an_authored_summary(routes):
    """summary 를 **사람이 썼는지** 본다.

    비어 있는지로는 검사가 안 된다 — 주지 않으면 FastAPI 가 함수명을 제목화해서
    (`create_product` → "Create Product") 채운다. 그 규칙은 절대 실패하지 않는
    장식이 된다(실제로 fail-on-revert 가 잡았다).
    """
    generated = [
        f"{sorted(route.methods)} {route.path}"
        for route in routes
        if not route.summary or route.summary == route.name.replace("_", " ").title()
    ]

    assert not generated, f"summary 가 함수명 자동 생성값 그대로다: {generated}"


def test_every_operation_has_a_description(operations):
    missing = [f"{m.upper()} {p}" for m, p, op in operations if not op.get("description")]

    assert not missing, f"description 이 없다: {missing}"


def test_every_path_parameter_is_described(operations):
    """경로 파라미터 설명이 없으면 사용자가 무엇을 넣을지 모른다."""
    missing = [
        f"{m.upper()} {p} :: {param.get('name')}"
        for m, p, op in operations
        for param in op.get("parameters", [])
        if param.get("in") == "path" and not param.get("description")
    ]

    assert not missing, f"설명 없는 path 파라미터: {missing}"


def test_every_query_parameter_is_described(operations):
    missing = [
        f"{m.upper()} {p} :: {param.get('name')}"
        for m, p, op in operations
        for param in op.get("parameters", [])
        if param.get("in") == "query" and not param.get("description")
    ]

    assert not missing, f"설명 없는 query 파라미터: {missing}"


# =============================================================================
# 5. schema 이름 — 모듈 경로가 새어 나오지 않아야 한다 (DOC-005)
# =============================================================================
def test_schema_names_do_not_leak_module_paths(schemas):
    """schema key 에 ``__`` 가 있으면 이름 충돌이 났다는 뜻이다.

    서로 다른 모듈에 같은 이름의 Pydantic class 가 있으면 FastAPI 는
    ``app__features__auth__schemas__auth_schema__UserResponse`` 같은 key 를 만든다.
    그 이름은 **파일을 옮기는 순간 바뀌고**, 그때 이 스키마로 생성한 클라이언트
    코드가 통째로 깨진다. 이름이 겹치면 둘 중 하나를 고쳐야 한다.
    """
    leaked = sorted(name for name in schemas if "__" in name)

    assert not leaked, (
        f"모듈 경로가 노출된 schema 이름: {leaked}. "
        "서로 다른 모듈의 같은 class 이름 때문이다 — 한쪽을 고유하게 바꿀 것."
    )


def test_public_dto_class_names_are_globally_unique():
    """공개 DTO class 이름이 프로젝트 전체에서 고유하다.

    위 규칙은 **결과**를 본다. 이 규칙은 **원인**을 본다 — schema 로 노출되지 않는
    class 라도 이름이 겹쳐 있으면 다음에 응답 모델로 쓰는 순간 터진다.
    """
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    seen: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(repo_root.joinpath("app").rglob("schemas/*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                seen[node.name].append(str(path.relative_to(repo_root)))

    assert seen, "schemas 디렉터리에서 class 를 하나도 못 찾았다 — 검사가 헛통과한다"
    collisions = {name: paths for name, paths in seen.items() if len(paths) > 1}

    assert not collisions, f"공개 DTO 이름이 겹친다: {collisions}"


# =============================================================================
# 6. 예시와 스냅샷 — 문서가 "읽을 만한가"
# =============================================================================
def _has_example(schema: dict[str, Any]) -> bool:
    """schema 자체 또는 속성 중 하나가 예시를 갖는지."""
    if "examples" in schema or "example" in schema:
        return True
    return any(
        "examples" in prop or "example" in prop for prop in schema.get("properties", {}).values()
    )


def test_example_feature_dtos_carry_examples(schemas):
    """ORM/Raw 예제 DTO 는 예시를 갖는다.

    예시 없는 스키마는 Scalar 에서 필드 목록만 보인다 — 이 두 기능은 **읽히려고**
    있는 것이라 그 상태면 존재 이유가 절반 사라진다. 기존 도메인 DTO 까지 강제하지는
    않는다(이번 작업의 범위가 아니다).
    """
    missing = sorted(name for name in REQUIRED_EXAMPLE_SCHEMAS if not _has_example(schemas[name]))

    assert not missing, f"예제 DTO 에 예시가 없다: {missing}"


def test_error_response_uses_openapi_31_examples(spec, schemas):
    """오류 모델이 선언된 OpenAPI 버전의 예시 문법을 쓴다.

    3.0 의 ``example``(단수)은 3.1 의 키워드가 아니다 — 도구에 따라 조용히 무시된다.
    이 스키마는 모든 오류 응답에 나오므로 여기서 틀리면 전부 예시가 사라진다.
    """
    assert spec["openapi"].startswith("3.1"), f"OpenAPI 버전이 바뀌었다: {spec['openapi']}"

    error = schemas["ErrorResponse"]
    assert "examples" in error, "ErrorResponse 에 3.1 형식 examples 가 없다"
    assert "example" not in error, "3.0 형식 example(단수)이 남아 있다"


def test_error_response_fields_are_described(schemas):
    """오류 모델의 필드 설명이 있다 — 클라이언트가 무엇을 분기할지 알아야 한다."""
    undescribed = sorted(
        name
        for name, prop in schemas["ErrorResponse"]["properties"].items()
        if not prop.get("description")
    )

    assert not undescribed, f"설명 없는 ErrorResponse 필드: {undescribed}"


def test_core_schema_snapshot_is_unchanged(schemas):
    """예제 DTO 의 **필드 집합과 필수 여부**를 스냅샷으로 고정한다.

    전체 JSON 을 비교하지 않는 이유는, 그러면 설명 한 줄만 고쳐도 실패해서 아무도
    보지 않게 되기 때문이다. 조용히 깨지면 클라이언트가 깨지는 것 — **필드 이름과
    필수 여부** — 만 잠근다.
    """
    snapshot = {
        "DailySalesItem": (
            ("gross_amount", "order_count", "sales_date"),
            ("gross_amount", "order_count", "sales_date"),
        ),
        "DailySalesReportResponse": (
            ("end_date", "items", "order_count", "start_date"),
            ("end_date", "items", "order_count", "start_date"),
        ),
        "ProductCreate": (
            ("description", "is_active", "name", "price", "sku", "stock"),
            ("name", "price", "sku"),
        ),
        "ProductResponse": (
            (
                "created_at",
                "description",
                "id",
                "is_active",
                "name",
                "price",
                "sku",
                "stock",
                "updated_at",
            ),
            ("created_at", "id", "name", "price", "sku", "updated_at"),
        ),
        "ProductListResponse": (
            ("items", "limit", "skip", "total"),
            ("items", "limit", "skip", "total"),
        ),
    }

    actual = {
        name: (
            tuple(sorted(schemas[name]["properties"])),
            tuple(sorted(schemas[name].get("required", []))),
        )
        for name in snapshot
    }

    assert actual == snapshot, (
        "예제 DTO 의 필드 집합 또는 필수 여부가 바뀌었다. "
        f"의도한 변경이면 이 스냅샷을 함께 고칠 것: {actual}"
    )
