"""/admin 로그인을 **실제 브라우저로** 한다 (admin-login ADR-003).

HTTP 테스트(``tests/core/test_admin_login_flow.py``)는 폼을 직접 POST 한다. 여기서는 사람이
하는 그대로 — Chromium 으로 로그인 화면을 열고, 입력란에 쓰고, 버튼을 누른다. 그래야
레이블·``required``·폼 ``action``·CSRF hidden 입력·쿠키(``SameSite=Strict``·``path=/admin``)가
브라우저에서 실제로 맞물리는지, Bootstrap CSS 가 SRI 검증을 통과해 적용되는지, 로그인 뒤 모든 관리
뷰의 목록과 ``created_at`` 날짜 필터가 열리는지 보인다.

대기는 ``load`` 로 한다 — ``networkidle`` 은 외부 CDN(Bootstrap) 지연에 묶여 CI 가 실패한 적이 있다.

계정은 ``python -m scripts.create_superuser --password-stdin`` 을 live server 와 같은 환경으로
실행해 만든다(사용자명은 매번 새로).
"""

from __future__ import annotations

import subprocess  # noqa: S404 - 운영 절차 그대로 스크립트를 실행한다
import sys
from uuid import uuid4

import pytest

from tests.browser.conftest import INSTALL_HINT, REPO_ROOT, server_env

pytestmark = pytest.mark.browser

PASSWORD = "Browser-admin-pw-123"

#: Bootstrap 5.3 의 ``.btn-primary`` 배경색 — CSS 가 적용됐다는 신호(SRI 가 틀리면 막혀 기본색이다).
BOOTSTRAP_PRIMARY = "rgb(13, 110, 253)"


def _create_superuser(username: str) -> None:
    # 한 줄로 두는 이유: `-X utf8` 계약 검사가 줄 단위다(tests/test_layering_and_openapi.py).
    launcher = [sys.executable, "-X", "utf8", "-m", "scripts.create_superuser"]
    result = subprocess.run(  # noqa: S603 - 인터프리터·모듈이 고정돼 있다
        [*launcher, "--username", username, "--email", f"{username}@x.com", "--password-stdin"],
        input=f"{PASSWORD}\n",
        cwd=REPO_ROOT,
        env=server_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-2000:]


def _admin_identities() -> list[str]:
    """설치 앱이 등록하는 관리 뷰의 URL 이름 — 운영과 같은 registry 경로로 모은다."""
    from app.core.apps import Apps
    from config import INSTALLED_APPS

    registry = Apps()
    registry.populate(INSTALLED_APPS, run_ready=False)
    identities = [
        view.identity
        for config in registry.get_app_configs()
        for view in (config.import_admin_views() or [])
    ]
    assert identities, "관리 뷰가 하나도 없다 — 검사가 헛통과한다"
    return identities


async def test_superuser_logs_in_through_the_bootstrap_screen(live_server: str):
    from playwright.async_api import async_playwright

    username = f"browser-{uuid4().hex[:10]}"
    _create_superuser(username)

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - 브라우저 미설치 시에만
            pytest.fail(f"Chromium 을 띄우지 못했다: {exc}\n준비: {INSTALL_HINT}")
        try:
            page = await browser.new_page()
            await page.goto(f"{live_server}/admin/", wait_until="load")
            assert page.url.endswith("/admin/login"), f"로그인 화면으로 가지 않았다: {page.url}"

            color = await page.eval_on_selector(
                "button[type=submit]", "el => getComputedStyle(el).backgroundColor"
            )
            assert color == BOOTSTRAP_PRIMARY, f"Bootstrap CSS 가 적용되지 않았다(SRI?): {color}"

            # 폼이 CSRF 토큰을 싣는다 — 브라우저는 hidden 입력을 그대로 보낸다(security-ops-hardening ADR-004).
            token = await page.get_attribute("form input[name=csrf_token]", "value")
            assert token and len(token) >= 43, f"CSRF hidden 입력이 비었다: {token!r}"

            await page.get_by_label("사용자명").fill(username)
            await page.get_by_label("비밀번호").fill("wrong-password")
            await page.get_by_role("button", name="로그인").click()
            await page.wait_for_load_state("load")
            assert await page.locator(".alert-danger").count() == 1

            await page.get_by_label("사용자명").fill(username)
            await page.get_by_label("비밀번호").fill(PASSWORD)
            await page.get_by_role("button", name="로그인").click()
            await page.wait_for_url(f"{live_server}/admin/", wait_until="load")

            # 등록된 모든 관리 뷰의 목록이 열린다 — 필터 정의가 깨지면 목록이 500 이다(F-007).
            # created_at 날짜 필터(지역 날짜 → UTC 범위)도 모든 목록에서 200 이다(ADR-005).
            for identity in _admin_identities():
                for query in ("", "?created_at=2026-10-12&created_at_op=on"):
                    url = f"{live_server}/admin/{identity}/list{query}"
                    listing = await page.goto(url, wait_until="load")
                    assert listing is not None and listing.status == 200, f"{url}: {listing}"

            cookies = {c["name"]: c for c in await page.context.cookies()}
            assert cookies["admin_session"]["path"] == "/admin"
            assert cookies["admin_session"]["httpOnly"] is True
            assert cookies["admin_session"]["sameSite"] == "Strict"

            await page.goto(f"{live_server}/admin/logout", wait_until="load")
            await page.goto(f"{live_server}/admin/", wait_until="load")
            assert page.url.endswith("/admin/login"), "로그아웃 뒤에도 관리 화면이 열린다"
        finally:
            await browser.close()
