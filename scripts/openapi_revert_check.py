"""OpenAPI 규칙별 fail-on-revert — 결함을 하나씩 주입하고 해당 규칙만 깨지는지 본다.

규칙이 "지금 통과한다"는 것은 규칙이 **동작한다**는 뜻이 아니다. 아무것도 검사하지
않는 규칙도 통과한다. 그래서 각 규칙에 대해 그 규칙이 막으려는 결함을 실제로 넣고,
**그 규칙이** 실패하는지 확인한다.

복구는 반드시 finally 에서 한다 — 첫 판에서 예외가 나 복구를 건너뛰는 바람에
저장소를 깨진 상태로 남긴 적이 있다.
"""

import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Windows 콘솔 기본 인코딩(cp949)에서 한글 출력이 죽지 않도록 UTF-8 로 고정한다.
# 게이트가 결함을 출력하다 인코딩 예외로 죽으면 실제 결함이 가려진다(C-7).
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

PY = sys.executable  # 이 스크립트를 띄운 인터프리터. .venv 경로를 가정하지 않는다.

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 이 하네스는 **소스 파일을 고쳤다 되돌린다**. 두 판이 겹치면 A 가 주입한 상태를
#: B 가 "원본"으로 백업하고, A 가 복구한 뒤 B 가 그 백업을 다시 써서 **주입된 상태가
#: 저장소에 남는다**. `finally` 복구만으로는 못 막는다 — 실제로 게이트를 3개 동시에
#: 돌려 `tags_metadata.py` 에 주입 문구가 남는 것을 확인했다.
#:
#: 락 파일은 저장소가 아니라 temp 에 둔다 — 저장소에 두면 `git status` 를 더럽히고
#: 실수로 커밋될 수 있다. 저장소 경로를 해시해 키로 쓰므로 다른 체크아웃끼리는
#: 서로를 막지 않는다.
_LOCK_PATH = Path(tempfile.gettempdir()) / (
    "openapi-revert-check-" + hashlib.sha256(str(REPO_ROOT).encode()).hexdigest()[:16] + ".lock"
)
LOCK_TIMEOUT_SECONDS = 900.0


@contextlib.contextmanager
def exclusive_run(timeout: float = LOCK_TIMEOUT_SECONDS):
    """같은 저장소에서 이 하네스가 한 번에 하나만 돌게 한다.

    거절하지 않고 **기다린다** — 병렬 게이트는 순차화되면 그만이다.
    """
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"{timeout:.0f}s 동안 락을 못 잡았다: {_LOCK_PATH}. "
                    "죽은 프로세스가 남긴 락이면 그 파일을 지울 것."
                ) from None
            time.sleep(0.5)
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            _LOCK_PATH.unlink()


TAGS = "app/core/tags_metadata.py"
AUTH_SCHEMA = "app/features/auth/schemas/auth_schema.py"
AUTH_VIEW = "app/features/auth/api/routers/v1/auth.py"
BLOG_VIEW = "app/features/blog/api/routers/v1/blog.py"
CATALOG_VIEW = "app/features/catalog/api/routers/v1/products.py"
CATALOG_SCHEMA = "app/features/catalog/schemas/product_schema.py"
EXCEPTION = "app/core/exception.py"
BLOG_ROUTER = "app/features/blog/api/routers/router.py"

# (라벨, 검사할 테스트 이름, [(파일, 원본, 대체), ...])
#
# 주의: `response_model` 만 지우면 FastAPI 가 **반환 타입 어노테이션**에서 schema 를
# 다시 만들어낸다. 결함이 실제로 생기려면 둘 다 없애야 한다.
CASES = [
    (
        "operationId 중복",
        "test_operation_ids_are_unique",
        [(BLOG_VIEW, 'operation_id="getPost",', 'operation_id="listPosts",')],
    ),
    (
        "operationId 자동 생성값",
        "test_every_operation_id_is_authored",
        [(BLOG_VIEW, '    operation_id="getPost",\n', "")],
    ),
    (
        "선언 없는 태그 사용",
        "test_every_used_tag_is_declared",
        [(BLOG_ROUTER, 'tags=["Blog"]', 'tags=["Blogg"]')],
    ),
    (
        "쓰지 않는 태그 선언",
        "test_every_declared_tag_is_used",
        [
            (
                TAGS,
                "tags_metadata = [\n",
                'tags_metadata = [\n    {"name": "Analytics", "description": "미사용"},\n',
            )
        ],
    ),
    (
        "태그 없는 operation",
        "test_every_operation_carries_a_tag",
        [(BLOG_ROUTER, '    tags=["Blog"],\n', "")],
    ),
    (
        "'예정' 문구 잔재",
        "test_no_tag_claims_to_be_unimplemented",
        [(TAGS, "**인증 API**", "**인증 API (예정)**")],
    ),
    (
        "성공 응답 schema 누락",
        "test_success_responses_declare_a_schema",
        [
            (CATALOG_VIEW, "    response_model=ProductListResponse,\n", ""),
            (CATALOG_VIEW, ") -> ProductListResponse:", ") -> Any:"),
        ],
    ),
    (
        "예제 DTO 가 문서에서 사라짐",
        "test_example_dtos_reach_the_documentation",
        [
            (CATALOG_VIEW, "    response_model=ProductListResponse,\n", ""),
            (CATALOG_VIEW, ") -> ProductListResponse:", ") -> Any:"),
        ],
    ),
    (
        # `response_model` 로 주입하면 FastAPI 가 앱 기동 자체를 거부해 측정이 안 된다.
        # 이 저장소는 오류 응답을 `responses` dict 로 손수 쓰므로 그 경로로 주입한다 —
        # 실제로 뚫릴 수 있는 방식이 그쪽이다.
        "204 에 본문 선언 (수동 responses)",
        "test_no_content_responses_carry_no_body",
        [
            (
                CATALOG_VIEW,
                "_NOT_FOUND: dict[int | str, dict[str, Any]] = {\n",
                "_NOT_FOUND: dict[int | str, dict[str, Any]] = {\n"
                '    204: {"content": {"application/json": {"schema": {}}}},\n',
            )
        ],
    ),
    (
        "오류 응답이 공통 모델 미사용",
        "test_documented_error_responses_reference_the_shared_model",
        [(CATALOG_VIEW, '404: {"model": ErrorResponse,', '404: {"model": ProductResponse,')],
    ),
    (
        "summary 를 안 씀(자동 생성값)",
        "test_every_operation_has_an_authored_summary",
        [(CATALOG_VIEW, '    summary="상품 생성",\n', "")],
    ),
    (
        "description 누락",
        "test_every_operation_has_a_description",
        [
            (
                CATALOG_VIEW,
                '    description="새 상품을 등록합니다. `sku` 는 전역 고유해야 합니다.",\n',
                "",
            )
        ],
    ),
    (
        "path 파라미터 설명 누락",
        "test_every_path_parameter_is_described",
        [(CATALOG_VIEW, 'Path(..., description="상품 ID(UUID)")', "Path(...)")],
    ),
    (
        "query 파라미터 설명 누락",
        "test_every_query_parameter_is_described",
        [(CATALOG_VIEW, 'Query(False, description="판매 중인 상품만 조회")', "Query(False)")],
    ),
    (
        "예제 DTO 예시 제거",
        "test_example_feature_dtos_carry_examples",
        [
            (CATALOG_SCHEMA, 'examples=["SKU-1001"],', ""),
            (CATALOG_SCHEMA, 'examples=["기계식 키보드"]', ""),
            (CATALOG_SCHEMA, 'examples=["적축 87키"]', ""),
            (CATALOG_SCHEMA, 'examples=["129000.00"]', ""),
            (CATALOG_SCHEMA, "examples=[25]", ""),
            (CATALOG_SCHEMA, "examples=[True]", ""),
            (CATALOG_SCHEMA, '"examples": [{"price": "119000.00", "stock": 12}]', '"x": []'),
            (
                CATALOG_SCHEMA,
                '"examples": [\n                {\n                    "items"',
                '"x": [\n                {\n                    "items"',
            ),
        ],
    ),
    (
        "오류 모델이 3.0 문법(example) 사용",
        "test_error_response_uses_openapi_31_examples",
        [(EXCEPTION, '"examples": [', '"example": [')],
    ),
    (
        "오류 모델 필드 설명 제거",
        "test_error_response_fields_are_described",
        [(EXCEPTION, 'description="기계가 분기할 오류 코드. 도메인별 접두사를 쓴다.",', "")],
    ),
    (
        "예제 DTO 필드 집합 변경",
        "test_core_schema_snapshot_is_unchanged",
        [(CATALOG_SCHEMA, "    stock: int = Field(0, ge=0,", "    quantity: int = Field(0, ge=0,")],
    ),
    (
        "schema 이름 충돌 (모듈 경로 노출)",
        "test_schema_names_do_not_leak_module_paths",
        [
            (
                AUTH_SCHEMA,
                "class AuthenticatedUserResponse(BaseModel):",
                "class UserResponse(BaseModel):",
            ),
            (AUTH_VIEW, "AuthenticatedUserResponse", "UserResponse"),
        ],
    ),
    (
        "공개 DTO 이름 충돌 (원인 검사)",
        "test_public_dto_class_names_are_globally_unique",
        [
            (
                AUTH_SCHEMA,
                "class AuthenticatedUserResponse(BaseModel):",
                "class UserResponse(BaseModel):",
            )
        ],
    ),
]


def read(path: str) -> str:
    return open(path, encoding="utf-8", newline="").read()


def write(path: str, text: str) -> None:
    open(path, "w", encoding="utf-8", newline="").write(text)


def run_case(label: str, test_name: str, edits) -> str:
    backups = {path: read(path) for path, _, _ in edits}
    try:
        for path, old, new in edits:
            source = read(path)
            if old not in source:
                return f"SKIP (앵커 없음: {old[:40]!r})"
            write(path, source.replace(old, new))

        proc = subprocess.run(
            [
                PY,
                "-m",
                "pytest",
                "tests/test_openapi_contract.py",
                "-k",
                test_name,
                "-q",
                "-p",
                "no:cacheprovider",
                "--no-header",
            ],
            capture_output=True,
            text=True,
            errors="replace",
        )
        if (
            " no tests ran" in proc.stdout
            or "1 passed" not in proc.stdout
            and "failed" not in proc.stdout
        ):
            return f"확인 불가 (pytest 출력: {proc.stdout.strip().splitlines()[-1][:60]!r})"
        return "감지함" if "failed" in proc.stdout else "*** 놓침 ***"
    finally:
        # 예외가 나든 말든 원본으로 되돌린다.
        for path, text in backups.items():
            write(path, text)


with exclusive_run():
    results = [
        (label, test_name, run_case(label, test_name, edits)) for label, test_name, edits in CASES
    ]

print()
print(f"{'주입한 결함':<32} {'규칙':<50} 결과")
print("-" * 104)
bad = 0
for label, test_name, verdict in results:
    print(f"{label:<32} {test_name:<50} {verdict}")
    if verdict != "감지함":
        bad += 1
print("-" * 104)
print(f"총 {len(results)}건 · 감지 {len(results) - bad}건 · 문제 {bad}건")
sys.exit(1 if bad else 0)
