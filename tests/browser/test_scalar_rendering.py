"""Scalar 문서가 **브라우저에서 실제로 그려지는지** (DOC-004 · residual-risk 4).

`tests/test_openapi_contract.py` 는 스키마가 OpenAPI 3.1 규격에 맞는지 본다. 그건
필요조건이지 충분조건이 아니다 — 규격에 맞는 스키마를 렌더러가 못 그리면 사용자가
보는 것은 빈 화면이고, 그 사실은 어떤 스키마 검사도 잡지 못한다.

Scalar 는 브라우저에서 JavaScript 로 `/openapi.json` 을 가져와 화면을 만든다. 그래서
`TestClient` 로는 이 층을 볼 수 없다. 실제 uvicorn 을 띄우고 Chromium 으로 연다.

외부 요청은 실패로 세지 않는다:
    Scalar 는 자기 레지스트리(`api.scalar.com`)를 조회하다 404 를 받는다. 우리가
    통제할 수 없고 문서 렌더링에도 영향이 없다. 그걸 실패로 보면 오프라인에서 이
    파일이 영원히 빨간불이 된다. **우리 오리진** 요청만 본다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.browser

#: 사이드바에 반드시 나타나야 하는 태그. `tags_metadata.py` 의 선언과 같아야 한다.
EXPECTED_TAGS = (
    "Health",
    "Auth",
    "Home",
    "User",
    "Blog",
    "Reply",
    "SNS",
    "Catalog",
    "Sales Reports",
)


# =============================================================================
# 1. 그려지는가
# =============================================================================
async def test_scalar_page_renders(docs_page):
    """빈 화면이 아니다.

    Scalar 가 죽으면 HTTP 200 과 함께 거의 빈 body 가 남는다 — 200 만 보는 검사는
    그 상태를 통과시킨다.
    """
    body = await docs_page.inner_text("body")

    assert len(body) > 1_000, f"Scalar 가 그려지지 않았다 (body {len(body)}자)"


async def test_every_declared_tag_appears_in_the_sidebar(docs_page):
    """선언한 태그가 전부 화면에 나온다.

    스키마에 있어도 렌더러가 건너뛰면 사용자는 그 그룹을 찾지 못한다.
    """
    body = await docs_page.inner_text("body")
    missing = [tag for tag in EXPECTED_TAGS if tag not in body]

    assert not missing, f"사이드바에 없는 태그: {missing}"


async def test_markdown_tables_in_tag_descriptions_render_as_tables(docs_page):
    """태그 설명의 Markdown 표가 실제 `<table>` 이 된다.

    `Health` 태그 설명은 liveness/readiness 를 표로 설명한다. 렌더러가 Markdown 표를
    지원하지 않으면 파이프(`|`)가 그대로 노출돼 읽을 수 없는 문단이 된다 — 스키마
    검사로는 절대 알 수 없는 층이다.
    """
    body = await docs_page.inner_text("body")

    assert "liveness" in body, "Health 태그 설명이 렌더링되지 않았다"
    assert await docs_page.locator("table").count() > 0, "Markdown 표가 <table> 로 그려지지 않았다"
    assert "|---|" not in body, "Markdown 표 원문이 그대로 노출됐다"


# =============================================================================
# 2. 예시가 보이는가 — 예제 기능의 존재 이유
# =============================================================================
async def test_example_values_are_visible_in_the_catalog_section(docs_page, live_server: str):
    """ORM 예제의 `examples` 가 실제 화면에 나타난다.

    Phase 6 에서 DTO 에 예시를 넣었다. 스키마에 들어갔다는 것과 화면에 그려진다는
    것은 다르다 — 이 검사가 그 사이를 잇는다.
    """
    await docs_page.goto(
        f"{live_server}/docs#tag/catalog", wait_until="networkidle", timeout=30_000
    )
    await docs_page.wait_for_timeout(2_500)
    body = await docs_page.inner_text("body")

    for expected in ("상품 생성", "SKU-1001", "129000.00"):
        assert expected in body, f"Catalog 화면에 '{expected}' 가 보이지 않는다"


async def test_raw_example_section_renders(docs_page, live_server: str):
    """Raw 예제도 같은 수준으로 보인다 — 두 예제는 나란히 비교되라고 있다."""
    await docs_page.goto(
        f"{live_server}/docs#tag/sales-reports", wait_until="networkidle", timeout=30_000
    )
    await docs_page.wait_for_timeout(2_500)
    body = await docs_page.inner_text("body")

    assert "일별 매출 리포트" in body, "Sales Reports 화면이 그려지지 않았다"


# =============================================================================
# 3. 조용히 죽고 있지 않은가
# =============================================================================
async def test_no_failed_requests_to_our_origin(docs_page, live_server: str):
    """우리 서버로 간 요청 중 실패한 것이 없다.

    외부(`api.scalar.com`)는 세지 않는다 — 통제할 수 없고 렌더링에 영향이 없다.
    """
    ours = [url for url in docs_page.failed_requests if live_server in url]

    assert not ours, f"우리 오리진 요청이 실패했다: {ours}"


async def test_openapi_json_is_served_to_the_browser(docs_page, live_server: str):
    """Scalar 가 읽는 스키마 자체가 200 이고 파싱된다.

    화면이 그려진다는 것의 전제다. 이게 깨지면 위 검사들이 무엇 때문에 실패했는지
    좁힐 수 없다.
    """
    response = await docs_page.request.get(f"{live_server}/openapi.json")

    assert response.status == 200, f"/openapi.json 이 {response.status} 를 돌려줬다"
    payload = await response.json()
    assert payload["openapi"].startswith("3.1")
    assert len(payload["paths"]) > 20, "스키마에 경로가 거의 없다"
