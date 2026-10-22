"""HTML 가이드 사이트의 내용 계약 — 표가 코드와 어긋나면 실패한다.

링크·경로 실재는 ``test_docs_references.py`` 가 본다. 여기서는 그 검사가 녹색인 채로 내용이
틀렸던 자리(API 표·설정 표·Mermaid 버전·허브 링크)를 코드에서 직접 뽑은 값과 대조한다.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings

import config
from app.core.security.access import AccessPolicyGuard
from main import app

REPO_ROOT = Path(__file__).resolve().parents[1]
GUIDES = REPO_ROOT / "docs" / "guides"
GUIDE_PAGES = sorted(GUIDES.rglob("*.html"))
MERMAID_URL = "https://cdn.jsdelivr.net/npm/mermaid@11.12.0/dist/mermaid.esm.min.mjs"


class _Page(HTMLParser):
    """``<tbody>`` 의 행(셀 텍스트 목록)과 ``<a href>``·스타일시트 ``<link href>`` 를 모은다."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.links: list[str] = []
        self.stylesheets: list[str] = []
        self._in_body = False
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self.rows.append([])
        elif tag == "td" and self._in_body:
            self._cell = []
        elif tag == "a" and attr.get("href"):
            self.links.append(attr["href"] or "")
        elif tag == "link" and attr.get("rel") == "stylesheet":
            self.stylesheets.append(attr.get("href") or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "tbody":
            self._in_body = False
        elif tag == "td" and self._cell is not None:
            self.rows[-1].append("".join(self._cell).strip())
            self._cell = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


def _api_operations() -> set[tuple[str, str, str]]:
    """OpenAPI operation × ``AccessPolicyGuard`` 판정 — (메서드, 경로, 접근 수준)."""
    levels = AccessPolicyGuard().levels(app)
    expected = set()
    for path, item in app.openapi()["paths"].items():
        for method in item:
            (level,) = levels[(method.upper(), path)]
            expected.add((method.upper(), path, str(level)))
    return expected


def test_api_reference_matches_openapi_and_access_guard():
    """API 표의 (메서드, 경로, 접근 수준) == OpenAPI operation × ``AccessPolicyGuard`` 판정."""
    expected = _api_operations()
    rows = _parse(GUIDES / "reference" / "api.html").rows
    documented = {(row[0], row[1], row[2]) for row in rows if len(row) >= 3}
    assert documented == expected, (
        f"표에만 있음: {sorted(documented - expected)}\n"
        f"코드에만 있음: {sorted(expected - documented)}"
    )


def test_configuration_reference_lists_every_setting():
    """설정 표가 Settings 모델의 필드를 하나도 빠뜨리지 않는다."""
    fields = {
        name
        for obj in vars(config).values()
        if isinstance(obj, type) and issubclass(obj, BaseSettings) and obj is not BaseSettings
        for name in obj.model_fields
    }
    assert len(fields) > 50, "설정 필드를 못 찾았다 — 검사가 헛통과한다"
    documented = {row[0] for row in _parse(GUIDES / "reference" / "configuration.html").rows if row}
    assert not fields - documented, f"설정 표에 없는 설정: {sorted(fields - documented)}"


def test_feature_api_tables_are_subset_of_openapi_and_access_guard():
    """기능별 API 표(``features/*.html``)의 행도 OpenAPI × 가드 판정에 있는 그대로다."""
    expected = _api_operations()
    documented = {
        (page.name, (row[0], row[1], row[2]))
        for page in sorted((GUIDES / "features").glob("*.html"))
        for row in _parse(page).rows
        if len(row) >= 3 and row[1].startswith("/api/")
    }
    assert len(documented) > 10, "기능별 API 행을 못 찾았다 — 검사가 헛통과한다"
    wrong = sorted(item for item in documented if item[1] not in expected)
    assert not wrong, f"코드와 다른 기능별 API 행: {wrong}"


def _render_default(field: FieldInfo) -> str:
    """설정 표의 "코드 기본값" 표기 — bool 은 소문자, None 은 ``(없음)``, 나머지는 ``repr``."""
    value = field.get_default(call_default_factory=True)
    if isinstance(value, bool):
        return str(value).lower()
    return "(없음)" if value is None else repr(value)


#: 기본값을 줄여 적은 행 — 여러 줄 Markdown 이라 표에 그대로 싣지 않는다.
ABBREVIATED_DEFAULTS = frozenset({"DESCRIPTION"})


def test_configuration_reference_defaults_match_code():
    """설정 표의 "코드 기본값" 열이 Settings 필드 기본값과 같다."""
    defaults = {
        name: _render_default(field)
        for obj in vars(config).values()
        if isinstance(obj, type) and issubclass(obj, BaseSettings) and obj is not BaseSettings
        for name, field in obj.model_fields.items()
    }
    rows = _parse(GUIDES / "reference" / "configuration.html").rows
    documented = {row[0]: row[1] for row in rows if len(row) >= 2 and row[0] in defaults}
    assert len(documented) > 50, "설정 행을 못 찾았다 — 검사가 헛통과한다"
    wrong = sorted(
        f"{name}: 표 {shown!r} ≠ 코드 {defaults[name]!r}"
        for name, shown in documented.items()
        if name not in ABBREVIATED_DEFAULTS and shown != defaults[name]
    )
    assert not wrong, wrong


def test_mermaid_is_pinned_to_one_version():
    """Mermaid 도식이 있는 모든 가이드가 같은 고정 버전을 import 한다."""
    problems = []
    for page in GUIDE_PAGES:
        text = page.read_text(encoding="utf-8")
        urls = set(re.findall(r"https://[^\"'\s]*mermaid[^\"'\s]*", text))
        if 'class="mermaid"' in text and urls != {MERMAID_URL}:
            problems.append(f"{page.relative_to(REPO_ROOT).as_posix()}: {sorted(urls)}")
    assert not problems, problems


def test_hub_links_every_guide():
    """허브 ``docs/guides/index.html`` 이 그 아래 모든 HTML 을 링크한다."""
    hub = GUIDES / "index.html"
    linked = {(GUIDES / href.split("#")[0]).resolve() for href in _parse(hub).links}
    missing = [
        page.relative_to(GUIDES).as_posix()
        for page in GUIDE_PAGES
        if page != hub and page.resolve() not in linked
    ]
    assert not missing, f"허브가 링크하지 않는 가이드: {missing}"


def test_stylesheet_links_exist():
    """가이드의 ``<link rel="stylesheet" href>`` 가 실재하는 파일을 가리킨다."""
    broken = [
        f"{page.relative_to(REPO_ROOT).as_posix()} → {href}"
        for page in GUIDE_PAGES
        for href in _parse(page).stylesheets
        if not (page.parent / href).is_file()
    ]
    assert not broken, broken
