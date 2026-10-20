"""L4 — 관리 화면(Playwright Chromium + 실제 MySQL·Redis).

브라우저가 하는 일은 브라우저로 한다(폼 제출·삭제 모달의 ``$.ajax`` DELETE·일괄 삭제·필터 UI).
CSRF·로그아웃 메서드처럼 "브라우저라면 하지 않을 요청" 은 :class:`AdminClient`(httpx)로 직접 보낸다.

삭제 뒤 sqladmin 은 ``window.location.href`` 로 목록에 간다. 그 이동이 끝나기 전에 ``goto``·``close`` 하면
ERR_ABORTED 가 나거나 멈춘다 — DELETE 응답과 ``wait_for_url`` 을 둘 다 기다린다. 테스트마다 timeout 이 있다.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.e2e.conftest import BASE_URL, USER_PASSWORD, AdminClient, Stack, unique, wait_for
from tests.e2e.ledger import covers

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(300)]

KST = ZoneInfo("Asia/Seoul")

#: identity → (테이블, 검색 가능한 표식 열, 나머지 필수 열 SQL·값, 생성·수정·삭제 가능 여부)
VIEWS: dict[str, dict] = {
    "post": {
        "table": "blog_posts",
        "tag": "title",
        "extra": {"content": "본문"},
        "create": True,
        "edit": True,
        "delete": True,
    },
    "reply": {
        "table": "replies",
        "tag": "content",
        "extra": {},
        "create": True,
        "edit": True,
        "delete": True,
    },
    "sns-post": {
        "table": "sns_posts",
        "tag": "content",
        "extra": {"like_count": 0},
        "create": True,
        "edit": True,
        "delete": True,
    },
    "product": {
        "table": "catalog_products",
        "tag": "name",
        "extra": {"sku": None, "price": "1.00", "stock": 1, "is_active": 1},
        "create": True,
        "edit": True,
        "delete": True,
    },
    "user": {
        "table": "users",
        "tag": "username",
        "extra": {"email": None, "is_active": 1, "is_superuser": 0},
        "create": False,
        "edit": True,
        "delete": True,
    },
    "sales-order": {
        "table": "sales_orders",
        "tag": "customer",
        "extra": {"order_no": None, "total_amount": "3.00", "status": "paid", "ordered_at": None},
        "create": False,
        "edit": False,
        "delete": False,
    },
    "user-access-log": {
        "table": "user_access_logs",
        "tag": "user_agent",
        "extra": {
            "ip_address": "192.0.2.10",
            "request_path": "/seed",
            "request_method": "GET",
            "is_bot": 0,
        },
        "create": False,
        "edit": False,
        "delete": True,
        "no_updated_at": True,
    },
}


def local_day_at_noon_utc(day: date) -> datetime:
    return (
        datetime(day.year, day.month, day.day, 12, tzinfo=KST).astimezone(UTC).replace(tzinfo=None)
    )


def seed(stack: Stack, identity: str, tag: str, created: datetime) -> str:
    view = VIEWS[identity]
    row_id = str(uuid.uuid4())
    values = {"id": row_id, view["tag"]: tag, "created_at": created}
    if not view.get("no_updated_at"):
        values["updated_at"] = created
    for column, value in view["extra"].items():
        if value is None:  # 고유값이 필요한 열
            value = (
                created
                if column == "ordered_at"
                else (f"{tag}@example.com" if column == "email" else unique("u")[:30])
            )
        values[column] = value
    columns = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    stack.sql(f"INSERT INTO {view['table']} ({columns}) VALUES ({marks})", tuple(values.values()))  # noqa: S608
    return row_id


def exists(stack: Stack, identity: str, row_id: str) -> bool:
    return bool(stack.sql(f"SELECT 1 FROM {VIEWS[identity]['table']} WHERE id=%s", (row_id,)))  # noqa: S608


@pytest.fixture
async def page(stack: Stack) -> AsyncIterator:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context()
            yield await context.new_page()
        finally:
            await browser.close()


async def browser_login(page, username: str, password: str = USER_PASSWORD) -> None:
    await page.goto(f"{BASE_URL}/admin/login", wait_until="load")
    await page.get_by_label("사용자명").fill(username)
    await page.get_by_label("비밀번호").fill(password)
    await page.get_by_role("button", name="로그인").click()
    await page.wait_for_load_state("load")


async def csrf_header(page) -> dict[str, str]:
    token = await page.get_attribute('meta[name="csrf-token"]', "content")
    return {"X-CSRF-Token": token or ""}


async def browser_fetch(
    page, url: str, method: str = "GET", headers: dict | None = None
) -> tuple[int, str]:
    """브라우저 **안에서** 요청한다 — Playwright 의 ``page.request`` 는 ``http://`` 로 Secure 쿠키를 싣지 않는다
    (Chromium 은 127.0.0.1 을 안전한 출처로 보고 싣는다). 실제 사용자 브라우저와 같은 쿠키 규칙을 탄다."""
    return await page.evaluate(
        """async ([url, method, headers]) => {
            const r = await fetch(url, {method, headers, redirect: "manual"});
            return [r.status, await r.text()];
        }""",
        [url, method, headers or {}],
    )


# ── 1. 로그인 ─────────────────────────────────────────────────────────────
async def test_login_wrong_password_then_success(page, superuser):
    await browser_login(page, superuser["username"], "wrong-password")
    assert await page.locator(".alert-danger").count() == 1
    assert page.url.endswith("/admin/login")
    await browser_login(page, superuser["username"])
    assert page.url == f"{BASE_URL}/admin/"
    cookie = next(c for c in await page.context.cookies() if c["name"] == "admin_session")
    assert (cookie["secure"], cookie["httpOnly"], cookie["sameSite"], cookie["path"]) == (
        True,
        True,
        "Strict",
        "/admin",
    )
    covers("admin:login", "정상", "틀린비밀번호")


def test_login_without_csrf_is_403(admin_client: AdminClient, superuser):
    admin_client.csrf()  # 세션은 있지만 토큰을 싣지 않는다
    refused = admin_client.request(
        "POST", "/admin/login", data={"username": superuser["username"], "password": USER_PASSWORD}
    )
    assert refused.status_code == 403
    assert not admin_client.is_logged_in()
    covers("admin:login", "CSRF없음")


def test_admin_login_rate_limit(stack: Stack, superuser):
    stack.start_app(
        AUTH_LOGIN_MAX_ATTEMPTS="2", AUTH_LOGIN_IP_MAX_ATTEMPTS="50", AUTH_LOGIN_WINDOW_SECONDS="5"
    )
    try:
        client = AdminClient()
        try:
            statuses = [
                client.login(superuser["username"], "wrong-password").status_code for _ in range(3)
            ]
            assert statuses == [400, 400, 429], statuses
            keys = stack.redis().keys("rl:admin-login:user:127.0.0.1:*")
            assert keys and 0 < stack.redis().ttl(keys[0]) <= 5
            assert stack.redis().exists("rl:admin-login:ip:127.0.0.1")
            stack.snapshot_redis_keys()  # 로그인에 성공하면 사용자 키는 지워진다 — 지우기 전에 관찰
            wait_for(
                lambda: not stack.redis().keys("rl:admin-login:user:127.0.0.1:*"),
                12,
                "창이 만료되지 않았다",
            )
            assert client.login(superuser["username"]).status_code == 302
        finally:
            client.close()
    finally:
        stack.start_app()
    covers("admin:login", "레이트리밋")


# ── 2. 7 뷰 ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("identity", sorted(VIEWS))
async def test_view_list_detail_filters_export(stack: Stack, page, superuser, identity: str):
    tag = unique(f"t{identity[:4]}")
    today = datetime.now(KST).date()
    old, mid, recent = (today - timedelta(days=d) for d in (10, 5, 2))
    ids = {
        name: seed(stack, identity, f"{tag}-{name}", local_day_at_noon_utc(day))
        for name, day in (("old", old), ("mid", mid), ("recent", recent))
    }
    await browser_login(page, superuser["username"])

    async def listed(query: str) -> set[str]:
        response = await page.goto(
            f"{BASE_URL}/admin/{identity}/list?search={tag}{query}", wait_until="load"
        )
        assert response is not None and response.status == 200, query
        html = await page.content()
        return {name for name, row_id in ids.items() if row_id in html}

    assert await listed("") == {"old", "mid", "recent"}
    covers(f"admin:{identity}", "목록")
    detail = await page.goto(f"{BASE_URL}/admin/{identity}/details/{ids['mid']}", wait_until="load")
    assert detail is not None and detail.status == 200 and f"{tag}-mid" in await page.content()
    covers(f"admin:{identity}", "상세")

    assert await listed(f"&created_at={mid}&created_at_op=on") == {"mid"}
    assert await listed(f"&created_at={mid}&created_at_op=from") == {"mid", "recent"}
    assert await listed(f"&created_at={mid}&created_at_op=before") == {"old"}
    assert await listed(f"&created_at={old}~{mid}&created_at_op=between") == {"old", "mid"}
    covers(
        f"admin:{identity}", "날짜필터:on", "날짜필터:from", "날짜필터:before", "날짜필터:between"
    )

    # 기간 필터 UI — 사람이 하는 그대로: 연산 고르고 날짜 두 개 넣고 적용.
    await page.goto(f"{BASE_URL}/admin/{identity}/list?search={tag}", wait_until="load")
    form = page.locator("form[data-local-date-filter]")
    await form.locator("select").select_option("between")
    await form.locator("[data-date-start]").fill(str(mid))
    await form.locator("[data-date-end]").fill(str(recent))
    await form.locator("button[type=submit]").click()
    await page.wait_for_url("**created_at_op=between**", wait_until="load")
    html = await page.content()
    assert ids["mid"] in html and ids["recent"] in html and ids["old"] not in html
    covers(f"admin:{identity}", "기간필터UI")

    status, body = await browser_fetch(page, f"{BASE_URL}/admin/{identity}/export/csv")
    assert status == 200 and ids["old"] in body, status
    covers(f"admin:{identity}", "내보내기")


@pytest.mark.parametrize("identity", sorted(VIEWS))
async def test_view_create_edit_delete_bulk_or_refusal(
    stack: Stack, page, superuser, identity: str
):
    view = VIEWS[identity]
    tag = unique(f"w{identity[:4]}")
    now = datetime.now(UTC).replace(tzinfo=None)
    rows = [seed(stack, identity, f"{tag}-{n}", now) for n in range(4)]
    await browser_login(page, superuser["username"])

    # 생성 — 폼의 필수 칸만 채운다. 자동 필드(created_at 등)가 폼에 섞이면 저장이 늘 실패한다.
    if view["create"]:
        await page.goto(f"{BASE_URL}/admin/{identity}/create", wait_until="load")
        assert (
            await page.locator("#created_at, #updated_at, #id").count() == 0
        ), "자동 필드가 폼에 있다"
        made = f"{tag}-made"
        await _fill_required(page, view["tag"], made)
        await page.locator('input[type=submit][value="Save"]').click()
        await page.wait_for_url(f"**/admin/{identity}/list**", wait_until="load")
        assert stack.sql(
            f"SELECT 1 FROM {view['table']} WHERE {view['tag']}=%s", (made,)
        ), "생성이 저장되지 않았다"  # noqa: S608
        covers(f"admin:{identity}", "생성")
    else:
        assert (await browser_fetch(page, f"{BASE_URL}/admin/{identity}/create"))[0] == 403
        covers(f"admin:{identity}", "생성")

    # 수정
    if view["edit"]:
        await page.goto(f"{BASE_URL}/admin/{identity}/edit/{rows[0]}", wait_until="load")
        assert await page.locator("#created_at, #updated_at, #id, #hashed_password").count() == 0
        await page.fill(f"#{view['tag']}", f"{tag}-edited")
        await page.locator('input[type=submit][value="Save"]').click()
        await page.wait_for_url(f"**/admin/{identity}/list**", wait_until="load")
        stored = stack.sql(
            f"SELECT {view['tag']} AS v FROM {view['table']} WHERE id=%s", (rows[0],)
        )  # noqa: S608
        assert stored[0]["v"] == f"{tag}-edited", "수정이 저장되지 않았다"
    else:
        assert (await browser_fetch(page, f"{BASE_URL}/admin/{identity}/edit/{rows[0]}"))[0] == 403
    covers(f"admin:{identity}", "수정")

    if view["delete"]:
        # 단건 삭제 — 행의 삭제 모달
        await page.goto(f"{BASE_URL}/admin/{identity}/list?search={tag}-1", wait_until="load")
        await page.locator(f'tr:has-text("{rows[1]}") a[data-bs-target="#modal-delete"]').click()
        async with page.expect_response(lambda r: r.request.method == "DELETE") as deleted:
            await page.locator("#modal-delete-button").click()
        assert (await deleted.value).ok
        await page.wait_for_url(f"**/admin/{identity}/list**", wait_until="load")
        assert not exists(stack, identity, rows[1])
        covers(f"admin:{identity}", "삭제")

        # 일괄 삭제 — 체크박스 두 개 → Actions → Delete selected items
        await page.goto(f"{BASE_URL}/admin/{identity}/list?search={tag}", wait_until="load")
        for row_id in rows[2:]:
            await page.locator(f'tr:has-text("{row_id}") input.select-box').check()
        await page.locator("#dropdownMenuButton").click()
        await page.locator("#action-delete").click()
        async with page.expect_response(lambda r: r.request.method == "DELETE") as deleted:
            await page.locator("#modal-delete-button").click()
        assert (await deleted.value).ok, (await deleted.value).status
        await page.wait_for_url(f"**/admin/{identity}/list**", wait_until="load")
        assert not any(exists(stack, identity, r) for r in rows[2:])
        covers(f"admin:{identity}", "일괄삭제")
    else:
        await page.goto(f"{BASE_URL}/admin/{identity}/list", wait_until="load")
        status, _ = await browser_fetch(
            page,
            f"{BASE_URL}/admin/{identity}/delete?pks={rows[1]}",
            "DELETE",
            await csrf_header(page),
        )
        assert status == 403 and exists(stack, identity, rows[1])
        covers(f"admin:{identity}", "삭제", "일괄삭제")


async def _fill_required(page, tag_field: str, tag: str) -> None:
    await page.fill(f"#{tag_field}", tag)
    for field in await page.locator("form input[required], form textarea[required]").all():
        if await field.input_value():
            continue
        kind = await field.get_attribute("type")
        await field.fill("1" if kind == "number" else unique("v")[:30])


# ── 3. CSRF — 토큰 없는 상태 변경 ─────────────────────────────────────────
def test_state_changes_without_csrf_token_are_403(
    stack: Stack, admin_client: AdminClient, superuser
):
    assert admin_client.login(superuser["username"]).status_code == 302
    row = seed(stack, "post", unique("csrf"), datetime.now(UTC).replace(tzinfo=None))
    attempts = {
        "생성": admin_client.request(
            "POST", "/admin/post/create", data={"title": "x", "content": "y"}
        ),
        "수정": admin_client.request(
            "POST", f"/admin/post/edit/{row}", data={"title": "x", "content": "y"}
        ),
        "삭제": admin_client.request("DELETE", f"/admin/post/delete?pks={row}"),
        "로그아웃": admin_client.request("POST", "/admin/logout"),
    }
    assert {name: r.status_code for name, r in attempts.items()} == dict.fromkeys(attempts, 403)
    assert exists(stack, "post", row) and admin_client.is_logged_in()
    covers("admin:csrf", "생성", "수정", "삭제", "로그아웃")


# ── 4. 로그아웃 ───────────────────────────────────────────────────────────
def test_logout_is_post_only_and_kills_the_copied_cookie(admin_client: AdminClient, superuser):
    assert admin_client.login(superuser["username"]).status_code == 302
    assert admin_client.request("GET", "/admin/logout").status_code == 405
    copied = admin_client.cookie
    token = admin_client.csrf("/admin/")
    assert (
        admin_client.request("POST", "/admin/logout", data={"csrf_token": token}).status_code == 302
    )
    replay = AdminClient()
    try:
        replay.cookie = copied
        assert not replay.is_logged_in(), "로그아웃한 쿠키가 아직 통한다"
    finally:
        replay.close()
    covers("admin:logout", "GET405", "POST폐기")


# ── 5. 세션 만료·다른 세션 폐기 ───────────────────────────────────────────
def test_idle_and_absolute_session_expiry(stack: Stack, superuser):
    """설정 하한(60초)으로 줄여 실제 시간으로 본다 — 미사용 60초, 절대 120초."""
    stack.start_app(ADMIN_SESSION_IDLE_SECONDS="60", ADMIN_SESSION_MAX_AGE_SECONDS="120")
    try:
        idle = AdminClient()
        busy = AdminClient()
        try:
            assert idle.login(superuser["username"]).status_code == 302
            assert busy.login(superuser["username"]).status_code == 302
            started = time.monotonic()
            # 계속 쓰는 세션은 미사용 만료에 걸리지 않는다. 쓰지 않은 세션은 60초 뒤 끊긴다.
            while time.monotonic() - started < 62:
                assert busy.is_logged_in(), "쓰는 세션이 미사용 만료에 걸렸다"
                time.sleep(20)
            assert not idle.is_logged_in(), "미사용 만료가 동작하지 않았다"
            # 계속 써도 절대 만료(120초)는 넘기지 못한다.
            while time.monotonic() - started < 115:
                assert busy.is_logged_in()
                time.sleep(20)
            time.sleep(max(0, 122 - (time.monotonic() - started)))
            assert not busy.is_logged_in(), "절대 만료가 동작하지 않았다"
        finally:
            idle.close()
            busy.close()
    finally:
        stack.start_app()
    covers("admin:session", "미사용만료", "절대만료")


@pytest.mark.parametrize("change", ["deactivate", "demote", "delete"])
async def test_admin_screen_user_change_kills_that_users_other_sessions(
    stack: Stack, page, superuser, change
):
    victim = unique("victim")
    assert stack.create_superuser(victim, USER_PASSWORD).returncode == 0
    victim_id = stack.sql("SELECT id FROM users WHERE username=%s", (victim,))[0]["id"]
    other = AdminClient()
    try:
        assert other.login(victim).status_code == 302 and other.is_logged_in()
        await browser_login(page, superuser["username"])
        if change == "delete":
            await page.goto(f"{BASE_URL}/admin/user/list?search={victim}", wait_until="load")
            await page.locator(
                f'tr:has-text("{victim_id}") a[data-bs-target="#modal-delete"]'
            ).click()
            async with page.expect_response(lambda r: r.request.method == "DELETE") as deleted:
                await page.locator("#modal-delete-button").click()
            assert (await deleted.value).ok
            await page.wait_for_url("**/admin/user/list**", wait_until="load")
        else:
            await page.goto(f"{BASE_URL}/admin/user/edit/{victim_id}", wait_until="load")
            await page.uncheck("#is_active" if change == "deactivate" else "#is_superuser")
            await page.locator('input[type=submit][value="Save"]').click()
            await page.wait_for_url("**/admin/user/list**", wait_until="load")
        assert not other.is_logged_in(), f"{change} 뒤에도 그 사용자의 다른 관리 세션이 살아 있다"
        assert stack.redis().scard(f"admin:user_sessions:{victim_id}") == 0
    finally:
        other.close()
    covers("admin:session", f"관리화면{change}")


# ── 6. 관리 화면 끄기 ─────────────────────────────────────────────────────
def test_admin_disabled_removes_the_mount(stack: Stack, api):
    stack.start_app(ADMIN_DISABLED="true")
    try:
        for path in ("/admin", "/admin/", "/admin/login", "/admin/post/list"):
            assert api.get(path).status_code == 404, path
        assert "admin" not in api.get("/health").text
        assert "관리 화면 비활성화" in stack.app_output() and "SQLAdmin" not in stack.app_output()
    finally:
        stack.start_app()
    assert api.get("/admin/login").status_code == 200
    covers("admin:disabled", "404")
