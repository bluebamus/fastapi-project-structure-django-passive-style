"""인벤토리 대조 — 실제 앱에서 뽑은 대상과 이번 실행이 채운 칸을 맞춘다(빈 칸 = 실패).

파일 이름이 ``zz`` 로 시작해 다른 e2e 파일이 모두 끝난 뒤에 돈다. **전체 e2e 실행에서만** 의미가 있다
(``pytest -m e2e``) — 파일 하나만 돌리면 다른 층의 칸이 비어 실패한다.

대상(앱에서 뽑는다):
* API operation — ``app.openapi()`` 의 operationId × 7칸(정상·검증오류·미인증·권한부족·없음·잘못된메서드·접근정책)
* 관리 뷰 — ``app.state.admin`` 의 뷰 identity × 12칸
* Celery 태스크·beat 일정 — 워커와 같은 include 로 불러온 Celery 앱
* Redis 키 접두어 — Redis 를 쓰는 운영 코드의 키 리터럴(f-string)
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

from tests.e2e.conftest import REPO_ROOT, Stack
from tests.e2e.ledger import COVERED, OBSERVATIONS, SEEN_REDIS_KEYS

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(120)]

API_CELLS = ("정상", "검증오류", "미인증", "권한부족", "없음", "잘못된메서드", "접근정책")
ADMIN_CELLS = (
    "목록",
    "상세",
    "생성",
    "수정",
    "삭제",
    "일괄삭제",
    "내보내기",
    "날짜필터:on",
    "날짜필터:from",
    "날짜필터:before",
    "날짜필터:between",
    "기간필터UI",
)

_PUBLIC = "Public(익명 조회) — 인증을 요구하지 않는다. 접근정책 칸에서 익명 2xx 를 확인했다"
_ANY_LOGIN = "로그인 사용자 누구나 — 소유권·슈퍼유저 검사 대상이 아니다"
_NO_INPUT = "입력(본문·쿼리)이 없다 — 검증할 값이 없다"
_ID_ONLY = "입력이 경로 식별자 하나 — 형식 검증이 없고 없는 id 는 '없음' 칸에서 404(비-UUID 포함)"
_NO_ID = "경로에 식별자가 없다 — 없는 자원을 지목할 수 없다"
_AUTH_OPEN = "PublicWrite(인증 전 단계) — 권한 개념이 없다"

#: operationId → 칸 → 사유. 여기 없는 칸은 실행으로 채워져야 한다.
NOT_APPLICABLE: dict[str, dict[str, str]] = {
    "healthCheck": {"검증오류": _NO_INPUT, "미인증": _PUBLIC, "권한부족": _PUBLIC, "없음": _NO_ID},
    "readinessCheck": {
        "검증오류": _NO_INPUT,
        "미인증": _PUBLIC,
        "권한부족": _PUBLIC,
        "없음": _NO_ID,
    },
    "authRegister": {
        "미인증": "가입 — 인증 전 단계라 '틀린 자격' 이 없다(중복은 409)",
        "권한부족": _AUTH_OPEN,
        "없음": _NO_ID,
    },
    "authLogin": {"권한부족": _AUTH_OPEN, "없음": _NO_ID},
    "authRefresh": {"권한부족": _AUTH_OPEN, "없음": _NO_ID},
    "authLogout": {"권한부족": _AUTH_OPEN, "없음": _NO_ID},
    "authMe": {
        "검증오류": _NO_INPUT,
        "권한부족": "본인 정보 — 대상이 토큰의 주체뿐이다",
        "없음": _NO_ID,
    },
    "getAccessLogs": {"없음": _NO_ID},
    "getRecentAccessLogs": {"없음": _NO_ID},
    "getAccessLogStats": {"검증오류": _NO_INPUT, "없음": _NO_ID},
    "getDailySalesReport": {"없음": _NO_ID},
    "listUsers": {"없음": _NO_ID},
    "createUser": {"없음": _NO_ID},
    "getUser": {"검증오류": _ID_ONLY},
    "deleteUser": {"검증오류": _ID_ONLY},
    "createProduct": {"없음": _NO_ID},
    "getProduct": {"검증오류": _ID_ONLY, "미인증": _PUBLIC, "권한부족": _PUBLIC},
    "listProducts": {"미인증": _PUBLIC, "권한부족": _PUBLIC, "없음": _NO_ID},
    "deleteProduct": {"검증오류": _ID_ONLY},
}
for _kind in ("Post", "Reply", "SnsPost"):
    _plural = {"Post": "Posts", "Reply": "Replies", "SnsPost": "SnsPosts"}[_kind]
    NOT_APPLICABLE[f"create{_kind}"] = {"권한부족": _ANY_LOGIN, "없음": _NO_ID}
    NOT_APPLICABLE[f"list{_plural}"] = {"미인증": _PUBLIC, "권한부족": _PUBLIC, "없음": _NO_ID}
    NOT_APPLICABLE[f"get{_kind}"] = {"검증오류": _ID_ONLY, "미인증": _PUBLIC, "권한부족": _PUBLIC}
    NOT_APPLICABLE[f"delete{_kind}"] = {"검증오류": _ID_ONLY}

#: 시나리오·장애·운영·로그 — 계획서 §3 의 항목.
EXPECTED_OTHER: dict[str, tuple[str, ...]] = {
    "harness": ("기동", "복제"),
    "scenario": (
        "L3-1 인증 수명",
        "L3-2 레이트 리밋",
        "L3-3 소유권",
        "L3-4 is_active",
        "L3-4 is_superuser",
        "L3-4 email",
        "L3-4 delete",
        "L3-5 접속 로그 적재·조회",
        "L3-5 보존 삭제",
        "L3-6 매출",
        "L3-8 replica 읽기",
        "L3-8 sticky·지연",
        "L3-8 가입 직후 /me 지연",
    ),
    "admin:login": ("정상", "틀린비밀번호", "CSRF없음", "레이트리밋"),
    "admin:logout": ("GET405", "POST폐기"),
    "admin:csrf": ("생성", "수정", "삭제", "로그아웃"),
    "admin:session": (
        "미사용만료",
        "절대만료",
        "관리화면deactivate",
        "관리화면demote",
        "관리화면delete",
    ),
    "admin:disabled": ("404",),
    "redis:celery": ("broker·backend",),
    "fault": (
        "Redis 정지",
        "Redis 재기동",
        "primary 정지",
        "replica 정지",
        "worker 정지",
        "CSRF 본문 측정",
    ),
    "ops": (
        "Alembic 왕복",
        "create_superuser 생성",
        "create_superuser 중복",
        "create_superuser 비밀번호·세션 폐기",
        "create_superuser 입력 거부",
        "기동 거부:ADMIN",
        "기동 거부:ADMIN_SESSION_IDLE_SECONDS",
        "기동 거부:ACCESS_TOKEN_SECRET_KEY",
        "기동 거부:Redis 버전",
        "기동 거부:접근 정책 미선언",
        "인증 캐시 빈 상태 첫 연결",
    ),
    "logging": (
        "실행 경로별 형식",
        "프로세스별 파일",
        "기동 초기 줄",
        "앱별 레벨",
        "크기 회전",
        "보관일수 삭제",
    ),
}


def redis_key_patterns() -> dict[str, str]:
    """Redis 를 쓰는 운영 코드의 키 리터럴 → 관찰 키와 맞출 glob."""
    found: dict[str, str] = {}
    literal = re.compile(r'f?"([a-z][a-z-]*:[^"\s]*)"')
    for path in sorted((REPO_ROOT / "app").rglob("*.py")):
        if "tests" in path.parts:
            continue
        text = path.read_text("utf-8")
        if "redis" not in text.lower() and "limiter" not in text.lower():
            continue
        for match in literal.finditer(text):
            raw = match.group(1)
            if raw == "rl:":  # 레이트 리밋 접두어 — 아래 키들의 앞에 붙는다
                found[raw] = "rl:*"
                continue
            found[raw] = "*" + re.sub(r"\{[^}]*\}", "*", raw)
    return found


def inventory() -> dict[str, tuple[str, ...]]:
    from main import app
    from tests.e2e.openapi_check import operations

    items: dict[str, tuple[str, ...]] = {f"op:{op}": API_CELLS for op in operations()}
    items.update({f"admin:{view.identity}": ADMIN_CELLS for view in app.state.admin._views})

    from app.celery.app import celery_app

    celery_app.loader.import_default_modules()
    items.update(
        {f"task:{name}": ("실행",) for name in celery_app.tasks if not name.startswith("celery.")}
    )
    items.update({f"beat:{name}": ("등록",) for name in celery_app.conf.beat_schedule})
    items.update(EXPECTED_OTHER)
    return items


def test_every_inventory_cell_is_filled_or_explained(stack: Stack):
    items = inventory()
    blanks, stale = [], []
    for item, cells in sorted(items.items()):
        reasons = NOT_APPLICABLE.get(item.removeprefix("op:"), {}) if item.startswith("op:") else {}
        for cell in cells:
            done = cell in COVERED.get(item, set())
            if done and cell in reasons:
                stale.append(f"{item}/{cell}: 실행됐는데 N/A 사유가 남아 있다")
            if not done and not reasons.get(cell):
                blanks.append(f"{item}/{cell}")
    _write_table(stack, items)
    assert not blanks, f"빈 칸 {len(blanks)}개: {blanks[:40]}"
    assert not stale, stale


def test_every_redis_key_prefix_in_code_was_observed(stack: Stack):
    stack.snapshot_redis_keys()
    patterns = redis_key_patterns()
    assert len(patterns) >= 10, f"키 리터럴 추출이 헛돈다: {patterns}"
    unseen = {
        raw: glob
        for raw, glob in patterns.items()
        if not any(fnmatch.fnmatchcase(k, glob) for k in SEEN_REDIS_KEYS)
    }
    assert not unseen, f"코드에는 있는데 실행 중 한 번도 보지 못한 Redis 키: {unseen}"


def _write_table(stack: Stack, items: dict[str, tuple[str, ...]]) -> None:
    """대조표와 관측을 실행 디렉터리에 남긴다(CI 산출물·보고용)."""
    rows = []
    for item, cells in sorted(items.items()):
        reasons = NOT_APPLICABLE.get(item.removeprefix("op:"), {}) if item.startswith("op:") else {}
        marks = [
            f"{cell}="
            + (
                "O"
                if cell in COVERED.get(item, set())
                else (f"N/A({reasons[cell]})" if cell in reasons else "빈칸")
            )
            for cell in cells
        ]
        rows.append(f"{item} | " + " | ".join(marks))
    target: Path = stack.run_dir / "inventory-table.txt"
    target.write_text("\n".join(rows) + "\n", "utf-8")
    (stack.run_dir / "observations.txt").write_text("\n".join(sorted(OBSERVATIONS)) + "\n", "utf-8")
    stack.outputs.extend([target, stack.run_dir / "observations.txt"])
