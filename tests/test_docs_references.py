"""문서가 참조하는 심볼·경로·환경변수가 실재하는지 (DOC-006).

`tests/test_docs_consistency.py` 는 문서에 **있으면 안 되는 문장**(passive-style 을
어기는 옛 절차)을 막는다. 이 파일은 반대 방향이다 — 문서가 **가리키는 대상이 실제로
존재하는지** 본다.

이게 따로 필요한 이유는 이번 작업에서 실제로 겪었기 때문이다. Phase 1 에서 세션
Dependency 이름을 바꾸고 Phase 7 에서 옛 이름을 지웠는데, 문서 21곳이 지워진 이름을
그대로 들고 있었다. 그 문서를 따라 하면 `ImportError` 가 난다. 코드 테스트는 전부
초록불이었다 — 문서는 아무것도 import 하지 않으니까.

**변경 이력은 제외한다.** 과거를 기록한 표에는 "그때 삭제한 파일" 이 나오는 것이
정상이다. 그것까지 실재를 요구하면 이력을 지우게 되고, 그러면 왜 그렇게 됐는지가
사라진다(요구명세 DOC-004 도 이력과 현재 절차를 구분하라고 한다).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 사용자가 "따라 하는" 문서 3종.
BASE_DOCS = ("README.md", "docs/ARCHITECTURE.md", "docs/QUICKSTART.md")

#: 변경 이력 섹션의 제목. 이 줄부터 문서 끝까지는 과거 기록이라 검사 대상이 아니다.
#: 번호가 붙을 수 있다 — `## 8. 변경 이력`.
HISTORY_HEADING = re.compile(r"^##\s*(?:\d+\.\s*)?(변경 이력|이력|Changelog)\s*$", re.MULTILINE)

#: Phase 1~7 에서 사라진 이름들. 문서에 남아 있으면 따라 하는 사람이 막힌다.
REMOVED_SYMBOLS = (
    # ADR-009 — Phase 7 에서 제거한 세션 Dependency 별칭
    "get_session",
    "get_read_session",
    "get_write_session",
    # ADR-016 — Phase 3b 에서 제거한 Repository 공개 메서드 중 대표 몇 개
    "get_by_id_with",
    "get_all_with",
    "bulk_create",
    "upsert",
)

#: 저장소 루트의 최상위 디렉터리. 경로 검사는 여기서 시작하는 것만 본다.
ROOT_DIRS = frozenset({"app", "docs", "tests", "scripts", "migrations"})

#: 대문자 심볼 중 환경변수가 아닌 것(알고리즘 이름·로그 레벨 등).
NON_ENV_UPPERCASE = frozenset(
    {
        "INSTALLED_APPS",
        "HS256",
        "INFO",
        "DEBUG",
        "ADMIN",
        "ADMIN_VIEWS",
        "GET",
        "POST",
        "PATCH",
        "PUT",
        "DELETE",
        "HTTP",
        "JSON",
        "SQL",
        "UUID",
        "API",
        "ORM",
        "CRUD",
        "README",
        "TODO",
    }
)


def _current_section(path: str) -> str:
    """변경 이력 앞부분 — 즉 **현재 절차**만 돌려준다."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    match = HISTORY_HEADING.search(text)
    return text[: match.start()] if match else text


def test_docs_under_test_exist():
    """검사 대상 문서가 실재한다 — 없으면 아래 규칙이 전부 헛통과한다."""
    missing = [path for path in BASE_DOCS if not (REPO_ROOT / path).exists()]

    assert not missing, f"검사 대상 문서가 없다: {missing}"


def test_current_section_is_not_empty():
    """변경 이력 자르기가 문서를 통째로 날리지 않았는지."""
    for path in BASE_DOCS:
        assert len(_current_section(path)) > 500, f"{path} 의 현재 절차 구간이 비었다"


@pytest.mark.parametrize("path", BASE_DOCS)
def test_docs_do_not_reference_removed_symbols(path: str):
    """제거된 심볼을 현재 절차에서 참조하지 않는다.

    Phase 7 에서 실제로 21곳이 걸렸다 — 세션 Dependency 옛 이름이 그대로 남아 있었다.
    """
    text = _current_section(path)
    # 코드 블록과 백틱 안만 본다 — 문서가 API 를 **가리킬 때** 쓰는 표기다.
    # 산문의 일반 명사("upsert 같은 쿼리는 …")까지 막으면 사라진 기능을 설명할 수 없다.
    fenced = re.findall(r"```.*?```", text, re.DOTALL)
    inline = re.findall(r"`[^`\n]+`", text)
    referenced = "\n".join(fenced + inline)
    stale = sorted(
        {
            name
            for name in REMOVED_SYMBOLS
            if re.search(rf"(?<![\w_]){re.escape(name)}(?![\w])", referenced)
        }
    )

    assert not stale, f"{path} 가 제거된 심볼을 코드/백틱으로 참조한다: {stale}"


@pytest.mark.parametrize("path", BASE_DOCS)
def test_referenced_repository_paths_exist(path: str):
    """백틱 안의 **저장소 루트 기준 경로**가 실재한다.

    루트에서 시작하는 것만 본다(`app/…`, `tests/…`). `db/session.py` 나
    `api/routers/router.py` 처럼 중간에서 시작하는 표기는 "각 기능 안의 그 위치"라는
    뜻이라 특정 파일을 가리키지 않는다 — 그것까지 실재를 요구하면 구조를 설명할 수 없다.
    """
    text = _current_section(path)
    pattern = re.compile(r"`([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.(?:py|ya?ml|toml|md|json|ini))`")
    here = (REPO_ROOT / path).parent

    targets = {m.group(1) for m in pattern.finditer(text)}
    rooted = {t for t in targets if t.split("/", 1)[0] in ROOT_DIRS}

    assert rooted, f"{path} 에서 루트 기준 경로를 하나도 못 찾았다 — 검사가 헛통과한다"

    # 저장소 루트 기준과 **문서 자신의 디렉터리** 기준 둘 다 허용한다 — 문서 사이의
    # 링크는 상대 경로로 쓰는 것이 자연스럽다.
    dead = [
        target
        for target in targets
        if not (REPO_ROOT / target).exists() and not (here / target).exists()
        if target.split("/", 1)[0] in ROOT_DIRS
    ]

    assert not dead, f"{path} 가 없는 경로를 가리킨다: {sorted(dead)}"


@pytest.mark.parametrize("path", BASE_DOCS)
def test_referenced_env_vars_exist_in_example(path: str):
    """문서가 안내하는 환경변수가 `.env.example` 에 있다.

    없으면 사용자가 그 키를 넣어도 Settings 가 읽지 않는다 — 조용히 기본값으로 동작한다.
    """
    declared = {
        line.split("=", 1)[0].strip().lstrip("# ").strip()
        for line in (REPO_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if "=" in line
    }
    assert declared, ".env.example 에서 키를 하나도 못 찾았다 — 검사가 헛통과한다"

    text = _current_section(path)
    unknown = sorted(
        {
            name
            for name in re.findall(r"`([A-Z][A-Z0-9_]{3,})`", text)
            if name not in declared and name not in NON_ENV_UPPERCASE
        }
    )

    assert not unknown, f"{path} 가 `.env.example` 에 없는 환경변수를 안내한다: {unknown}"


def test_installed_apps_example_lists_every_installed_app():
    """`ARCHITECTURE.md` 의 등록 예제가 실제 `INSTALLED_APPS` 를 전부 담는다."""
    from config import INSTALLED_APPS

    text = _current_section("docs/ARCHITECTURE.md")
    missing = [entry for entry in INSTALLED_APPS if entry not in text]

    assert not missing, f"ARCHITECTURE.md 예제에 빠진 앱: {missing}"


def test_session_dependency_names_in_docs_are_importable():
    """문서에 나오는 세션 Dependency 이름이 실제로 import 된다.

    "옛 이름이 없다"의 짝이다 — 새 이름을 잘못 적었을 때도 잡아야 한다.
    """
    from app.core.db import session as db_session

    names = set()
    for path in BASE_DOCS:
        names |= set(re.findall(r"(get_[a-z_]*db_session)", _current_section(path)))

    assert names, "문서에서 세션 Dependency 이름을 하나도 못 찾았다 — 검사가 헛통과한다"
    missing = sorted(name for name in names if not hasattr(db_session, name))

    assert not missing, f"문서가 존재하지 않는 세션 Dependency 를 안내한다: {missing}"
