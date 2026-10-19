"""테스트용 /admin 로그인·로그아웃 — 브라우저가 하는 그대로 CSRF 토큰을 싣는다.

로그인: GET 이 세션(Redis)에 토큰을 두고 hidden 입력으로 싣는다(security-ops-hardening ADR-004).
로그인 이후: 관리 화면의 ``<meta name="csrf-token">`` 을 읽어 POST·DELETE 에 싣는다 — 브라우저에서는
덮어쓴 ``sqladmin/base.html`` 의 스크립트가 하는 일이다(admin-session-hardening ADR-002).
로그아웃은 POST 전용이다(ADR-003).
"""

from __future__ import annotations

import re

from httpx import AsyncClient, Response

CSRF_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')
CSRF_META = re.compile(r'<meta name="csrf-token" content="([^"]+)">')


async def admin_csrf_token(client: AsyncClient) -> str:
    """로그인 화면을 열어 hidden 입력의 CSRF 토큰을 꺼낸다(세션 쿠키는 client 가 받는다)."""
    page = await client.get("/admin/login")
    match = CSRF_INPUT.search(page.text)
    assert match, f"로그인 화면에 CSRF hidden 입력이 없다 (status={page.status_code})"
    return match.group(1)


async def admin_login(client: AsyncClient, username: str, password: str) -> Response:
    """CSRF 토큰을 실어 /admin/login 에 POST 한다."""
    token = await admin_csrf_token(client)
    return await client.post(
        "/admin/login",
        data={"username": username, "password": password, "csrf_token": token},
    )


async def admin_page_token(client: AsyncClient, path: str = "/admin/") -> str:
    """로그인 이후 관리 화면의 meta CSRF 토큰."""
    page = await client.get(path)
    match = CSRF_META.search(page.text)
    assert match, f"관리 화면에 CSRF meta 가 없다 (status={page.status_code})"
    return match.group(1)


async def admin_logout(client: AsyncClient) -> Response:
    """meta 토큰을 실어 /admin/logout 에 POST 한다."""
    token = await admin_page_token(client)
    return await client.post("/admin/logout", data={"csrf_token": token})
