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
import unicodedata
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 사용자가 "따라 하는" 현행 문서 3종 — 진입(README)·아키텍처·개발 가이드.
#:
#: 2026-09-17 재구성 전에는 진입 문서 3종 + ``docs/project-guide/<최신>/`` 을 따로 모았다.
#: 심화 가이드를 진입 문서에서 빼놓고 검사하지 않던 것이 L-007·L-008 이었다. 지금은
#: 심화 내용이 이 세 문서 안에 있으므로, 학습자가 따라 하는 문서 **전체**가 곧 이 목록이다.
ENTRY_DOCS = ("README.md", "docs/guides/ARCHITECTURE.md", "docs/guides/DEVELOPMENT.md")

#: 학습자가 실제로 따라 하는 문서 전체.
BASE_DOCS = ENTRY_DOCS

#: 재구성으로 사라진 문서 위치. 현행 문서가 이곳을 가리키면 학습자를 없는 문서로 보낸다.
#: HTML 안내서 2편(``server-lifecycle-guide.html``·``feature-development-guide.html``)은
#: 2026-09-17 재구성에서 지웠다가 같은 날 되살렸으므로 이 목록에서 뺐다 — 대신 아래
#: ``HTML_GUIDES`` 검사가 실재·링크·코드 경로를 본다.
RETIRED_DOC_LOCATIONS = (
    "docs/project-guide/",
    "project-guide/v",
    "docs/django-style-app-registry/",
    "QUICKSTART.md",
    "09-orm-vs-raw-decision.md",
)

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
        # SQL 키워드 — Raw SQL 예제가 늘면서 대문자로 자주 나온다.
        # (DELETE 는 위에 HTTP 메서드로 이미 있다)
        "SELECT",
        "INSERT",
        "UPDATE",
        "WITH",
        "FROM",
        "WHERE",
        "GROUP",
        "ORDER",
        "COUNT",
        "SUM",
        # MySQL 날짜 함수. 07 문서가 "SQL 이 아니라 Python 에서 계산하는 이유" 로 인용한다.
        "DATE_ADD",
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

    text = _current_section("docs/guides/ARCHITECTURE.md")
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


# =============================================================================
# 학습 경로 잠금 (T-3)
#
# 위의 검사들은 "문서가 **틀린 것**을 가리키지 않는가" 를 본다. 아래는 반대다 —
# "문서에 **있어야 할 것이 있는가**". 이 그룹의 결함(L-001·L-003·L-005·L-006)은
# 전부 후자였고, 그래서 어떤 검사도 실패하지 않은 채 학습 경로가 끊겨 있었다.
# =============================================================================

#: 진입 문서에 반드시 도달 경로가 있어야 하는 항목.
#: ``(라벨, 찾을 문자열, 최소 몇 개 문서에 있어야 하는가)``
REQUIRED_IN_ENTRY_DOCS: tuple[tuple[str, str, int], ...] = (
    # Raw 계층의 존재 자체. 이게 0 이던 것이 L-001 이다.
    ("Raw Repository Base", "RawRepositoryBase", 2),
    # 두 참조 예제로 가는 실제 경로.
    ("ORM 참조 예제", "app/features/catalog/repositories/product_repository.py", 2),
    ("Raw 참조 예제", "app/features/reports/repositories/sales_report_repository.py", 2),
    # 심화 문서로 나가는 문. 0 이던 것이 L-003 이다. 심화 내용은 아키텍처·개발 가이드가
    # 소유하므로, 각 문서가 나머지 둘 중 하나 이상에서 링크돼야 한다.
    ("아키텍처 문서 링크", "ARCHITECTURE.md", 2),
    ("개발 가이드 링크", "DEVELOPMENT.md", 2),
    # 선택 기준 절. "언제 ORM, 언제 Raw" 가 어디에도 없던 것이 L-004 다.
    ("ORM/Raw 결정 가이드", "DEVELOPMENT.md#orm-raw", 2),
)

#: ORM/Raw 결정 절의 앵커 — 위 링크가 가리키는 대상이 실제로 있어야 한다.
ORM_RAW_ANCHOR = '<a id="orm-raw"></a>'


@pytest.mark.parametrize(("label", "needle", "minimum"), REQUIRED_IN_ENTRY_DOCS)
def test_learning_path_is_reachable_from_entry_docs(label: str, needle: str, minimum: int):
    """학습 경로의 각 지점이 진입 문서에서 도달 가능하다."""
    found = [path for path in ENTRY_DOCS if needle in _current_section(path)]

    assert (
        len(found) >= minimum
    ), f"{label}({needle}) 가 진입 문서 {minimum}곳 이상에 없다 — 있는 곳: {found or '없음'}"


def test_orm_raw_anchor_exists():
    """``DEVELOPMENT.md#orm-raw`` 링크가 가리키는 앵커가 실제로 있다.

    파일 링크 검사는 ``#`` 뒤를 보지 않는다. 앵커가 사라지면 링크는 초록인 채로
    문서 첫머리에 떨어진다.
    """
    text = (REPO_ROOT / "docs" / "guides" / "DEVELOPMENT.md").read_text(encoding="utf-8")

    assert ORM_RAW_ANCHOR in text, f"DEVELOPMENT.md 에 {ORM_RAW_ANCHOR} 가 없다"


def test_entry_docs_do_not_point_at_retired_docs():
    """현행 문서가 재구성으로 사라진 문서 위치를 가리키지 않는다.

    옛 버전 가이드를 가리키던 검사의 후속이다 — 학습자를 옛 문서로 보내는 것은
    링크가 깨진 것보다 나쁘다. 깨진 링크는 눈에 띄지만 옛 경로 안내는 그럴듯하게 읽힌다.
    과거 기록(변경 이력)은 제외한다.
    """
    stale = {
        path: [loc for loc in RETIRED_DOC_LOCATIONS if loc in _current_section(path)]
        for path in ENTRY_DOCS
    }
    stale = {path: locs for path, locs in stale.items() if locs}

    assert not stale, f"현행 문서가 사라진 문서 위치를 가리킨다: {stale}"


def test_readme_title_identifies_this_repository():
    """README 첫 줄이 이 저장소를 식별한다.

    L-005 는 기준선 교체 때 다른 저장소의 제목이 남은 것이었다. 학습자가 **가장 먼저
    보는 한 줄**이라 틀리면 나머지를 다 의심하게 된다.
    """
    title = next(
        line
        for line in (REPO_ROOT / "README.md").read_text(encoding="utf-8").splitlines()
        if line.strip()
    )

    assert "Django Passive Style" in title, f"README 제목이 이 저장소를 식별하지 않는다: {title!r}"
    assert "Default" not in title, f"다른 저장소 이름 잔재가 README 제목에 있다: {title!r}"


def test_readme_structure_tree_lists_both_example_features():
    """README **구조 트리 안**에 두 참조 예제가 실물로 있다.

    ``<name>/`` 자리 표시자만 있으면 두 예제가 있다는 사실을 트리에서 알 수 없다(L-006).

    본문 전체가 아니라 트리 블록만 본다 — 다른 절에서 ``app/features/catalog/...`` 경로를
    인용하는 것만으로 이 검사가 통과하면, 트리에서 두 예제를 지워도 아무도 모른다.
    """
    text = _current_section("README.md")
    heading = text.index("## 프로젝트 구조")
    start = text.index("```", heading)
    tree = text[start : text.index("```", start + 3)]

    missing = [name for name in ("catalog/", "reports/") if name not in tree]

    assert not missing, f"README 구조 트리에 없는 예제 기능: {missing}"


# =============================================================================
# HTML 안내서 (2026-09-17 복원)
#
# HTML 은 Markdown 검사(백틱·``](...)`` 패턴)에 걸리지 않는다. 같은 성질 — 가리키는
# 대상이 실재하는가, 사라진 문서를 가리키지 않는가 — 을 HTML 표기(``<code>``·
# ``data-source``·``href``)로 따로 본다.
# =============================================================================

#: README 「문서 안내」가 나열하는 문서 — 이 순서가 계약이다.
DOC_INDEX_ORDER = (
    "README.md",
    "docs/guides/ARCHITECTURE.md",
    "docs/guides/DEVELOPMENT.md",
    "docs/guides/server-lifecycle-guide.html",
    "docs/guides/feature-development-guide.html",
    "docs/specs/orm-raw-repository/requirements.md",
    "docs/specs/orm-raw-repository/development-plan.md",
    "docs/specs/orm-raw-repository/workflow-guide.md",
    "docs/crp/groups/",
)

HTML_GUIDES = (
    "docs/guides/server-lifecycle-guide.html",
    "docs/guides/feature-development-guide.html",
)

#: ``<code>`` 안에서 저장소 루트 기준으로 해석하는 최상위 파일.
ROOT_FILES = frozenset(
    {"config.py", "main.py", "pyproject.toml", "compose.test.yaml", ".env.example", "alembic.ini"}
)

#: ``<code>`` 안의 경로 후보. 확장자로 파일 경로만 고른다.
CODE_PATH_PATTERN = re.compile(
    r"^\.?[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.(?:py|ya?ml|toml|md|html|ini|example)$"
)


class _HtmlScan(HTMLParser):
    """HTML 안내서에서 검사할 조각(id·href·data-source·code·날것 꺾쇠)을 모은다."""

    def __init__(self) -> None:
        # 엔티티를 풀지 않는다 — `&lt;` 는 정상, 본문에 남은 날것 `<`·`>` 만 잡는다.
        super().__init__(convert_charrefs=False)
        self.ids: set[str] = set()
        self.hrefs: list[str] = []
        self.sources: list[tuple[str, str | None]] = []
        self.codes: list[str] = []
        self.raw_brackets: list[str] = []
        self._skip = 0
        self._code_depth = 0
        self._code_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"] or "")
        if tag == "a" and values.get("href"):
            self.hrefs.append(values["href"] or "")
        if values.get("data-source"):
            self.sources.append((values["data-source"] or "", values.get("data-symbol")))
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "code":
            self._code_depth += 1
            self._code_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip -= 1
        if tag == "code" and self._code_depth:
            self._code_depth -= 1
            self.codes.append("".join(self._code_buf))

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if "<" in data or ">" in data:
            self.raw_brackets.append(data.strip()[:80])
        if self._code_depth:
            self._code_buf.append(data)


def _scan_html(path: str) -> _HtmlScan:
    scan = _HtmlScan()
    scan.feed((REPO_ROOT / path).read_text(encoding="utf-8"))
    scan.close()
    return scan


def _github_slug(heading: str) -> str:
    """GitHub 이 Markdown 제목에 붙이는 앵커 — 구두점·기호를 지우고 공백을 ``-`` 로."""
    kept = [
        char
        for char in heading.strip().lower()
        if char in "-_" or unicodedata.category(char)[0] not in ("P", "S")
    ]
    return "".join(kept).replace(" ", "-")


def _markdown_anchors(path: Path) -> set[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    anchors: set[str] = set(re.findall(r'<a id="([^"]+)"></a>', text))
    seen: dict[str, int] = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", text, re.MULTILINE):
        slug = _github_slug(heading)
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def _anchor_exists(target: Path, anchor: str) -> bool:
    if target.suffix == ".md":
        return anchor in _markdown_anchors(target)
    if target.suffix == ".html":
        scan = _HtmlScan()
        scan.feed(target.read_text(encoding="utf-8"))
        return anchor in scan.ids
    return True


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_exists_and_is_indexed_in_readme(path: str):
    """HTML 안내서가 실재하고 README 「문서 안내」에서 링크된다."""
    assert (REPO_ROOT / path).is_file(), f"{path} 가 없다"
    readme = _current_section("README.md")
    assert f"]({path})" in readme, f"README 문서 안내가 {path} 를 링크하지 않는다"


def test_readme_doc_index_lists_documents_in_order():
    """README 「문서 안내」 표가 약속한 머리글과 나열 순서를 지킨다."""
    readme = _current_section("README.md")
    start = readme.index("## 문서 안내")
    following = readme.find("\n## ", start + 5)
    section = readme[start : following if following != -1 else len(readme)]

    assert "| 문서 | 역할 | 언제 보나 |" in section, "문서 안내 표 머리글이 다르다"
    positions = []
    for doc in DOC_INDEX_ORDER:
        assert doc in section, f"문서 안내에 {doc} 가 없다"
        positions.append(section.index(doc))
    assert positions == sorted(positions), "문서 안내의 나열 순서가 약속과 다르다"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_data_sources_exist(path: str):
    """``data-source`` 가 실제 파일을, ``data-symbol`` 이 그 파일 안의 정의를 가리킨다."""
    scan = _scan_html(path)
    assert scan.sources, f"{path} 에서 data-source 를 하나도 못 찾았다 — 검사가 헛통과한다"

    problems = []
    for source, symbol in scan.sources:
        file = REPO_ROOT / source
        if not file.is_file():
            problems.append(f"없는 파일: {source}")
            continue
        if symbol and not re.search(
            rf"(?:def|class)\s+{re.escape(symbol)}\b|^{re.escape(symbol)}\s*=",
            file.read_text(encoding="utf-8"),
            re.MULTILINE,
        ):
            problems.append(f"{source} 에 {symbol} 정의가 없다")

    assert not problems, f"{path}: {sorted(set(problems))}"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_code_paths_exist(path: str):
    """``<code>`` 안의 저장소 경로(루트 디렉터리·최상위 파일)가 실재한다."""
    candidates = {code.strip() for code in _scan_html(path).codes}
    rooted = {
        c
        for c in candidates
        if CODE_PATH_PATTERN.match(c) and (c.split("/", 1)[0] in ROOT_DIRS or c in ROOT_FILES)
    }
    assert rooted, f"{path} 에서 루트 기준 경로를 하나도 못 찾았다 — 검사가 헛통과한다"

    dead = sorted(c for c in rooted if not (REPO_ROOT / c).exists())
    assert not dead, f"{path} 가 없는 경로를 가리킨다: {dead}"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_relative_links_and_anchors_resolve(path: str):
    """상대 ``href`` 가 실재하는 파일과 앵커를 가리킨다."""
    scan = _scan_html(path)
    here = (REPO_ROOT / path).parent
    broken = []
    for href in scan.hrefs:
        if href.startswith(("http://", "https://", "mailto:")):
            continue
        file_part, _, anchor = href.partition("#")
        if not file_part:
            if anchor not in scan.ids:
                broken.append(href)
            continue
        target = (here / file_part).resolve()
        if not target.exists() or (anchor and not _anchor_exists(target, anchor)):
            broken.append(href)

    assert not broken, f"{path} 의 깨진 링크: {broken}"


@pytest.mark.parametrize("path", BASE_DOCS)
def test_markdown_link_anchors_resolve(path: str):
    """Markdown 링크의 ``#앵커`` 가 대상 문서에 실재한다(파일 실재는 다른 검사가 본다)."""
    doc = REPO_ROOT / path
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", doc.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
            continue
        file_part, _, anchor = target.partition("#")
        resolved = (doc.parent / file_part).resolve() if file_part else doc
        if resolved.exists() and not _anchor_exists(resolved, anchor):
            broken.append(target)

    assert not broken, f"{path} 의 깨진 앵커: {broken}"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_text_escapes_angle_brackets(path: str):
    """본문 텍스트의 ``<``·``>`` 는 ``&lt;``·``&gt;`` 로 쓴다 — 날것이면 태그로 읽힐 수 있다."""
    raw = _scan_html(path).raw_brackets

    assert not raw, f"{path} 에 이스케이프되지 않은 꺾쇠가 있다: {raw[:5]}"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_does_not_point_at_retired_docs(path: str):
    """HTML 안내서가 재구성으로 사라진 문서 위치를 가리키지 않는다."""
    text = (REPO_ROOT / path).read_text(encoding="utf-8")
    stale = [loc for loc in RETIRED_DOC_LOCATIONS if loc in text]

    assert not stale, f"{path} 가 사라진 문서 위치를 가리킨다: {stale}"


@pytest.mark.parametrize("path", HTML_GUIDES)
def test_html_guide_does_not_reference_removed_symbols(path: str):
    """HTML 안내서의 ``<code>`` 가 제거된 심볼을 가리키지 않는다."""
    codes = "\n".join(_scan_html(path).codes)
    stale = sorted(
        name
        for name in REMOVED_SYMBOLS
        if re.search(rf"(?<![\w_]){re.escape(name)}(?![\w])", codes)
    )

    assert not stale, f"{path} 가 제거된 심볼을 가리킨다: {stale}"


def test_lifecycle_guide_appendix_lists_every_setting():
    """서버 수명주기 안내서 부록이 ``config.py`` 의 설정 필드를 빠짐없이 싣는다."""
    import inspect

    from pydantic_settings import BaseSettings

    import config as config_module

    codes = set(_scan_html("docs/guides/server-lifecycle-guide.html").codes)
    fields = {
        name
        for obj in vars(config_module).values()
        if inspect.isclass(obj) and issubclass(obj, BaseSettings) and obj is not BaseSettings
        for name in obj.model_fields
    }
    assert fields, "config.py 에서 설정 필드를 못 찾았다 — 검사가 헛통과한다"

    missing = sorted(fields - codes)
    assert not missing, f"server-lifecycle-guide.html 부록에 없는 설정: {missing}"
