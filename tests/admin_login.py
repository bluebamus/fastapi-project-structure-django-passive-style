"""테스트용 /admin 로그인 — 로그인 화면에서 CSRF 토큰을 받아 폼과 함께 보낸다.

브라우저가 하는 그대로다: GET 이 세션 쿠키에 토큰을 두고 hidden 입력으로 싣는다(security-ops-hardening
ADR-004). 토큰 없이 POST 하면 403 이므로, 로그인 흐름을 시험하는 테스트는 이 함수를 쓴다.
"""

from __future__ import annotations

import re

from httpx import AsyncClient, Response

CSRF_INPUT = re.compile(r'<input type="hidden" name="csrf_token" value="([^"]+)">')


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
