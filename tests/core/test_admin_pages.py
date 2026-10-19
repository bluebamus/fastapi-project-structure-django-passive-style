"""로그인한 슈퍼유저가 **모든** 관리 뷰의 목록·필터·상세를 연다 (admin-login F-007).

``column_filters`` 에 모델 컬럼을 그대로 넘기면 sqladmin 0.32 의 목록 처리(``filter_.parameter_name``)가
``AttributeError`` 로 죽는다 — 목록 페이지가 500 이 된다. ModelView 정의 검사
(``tests/core/test_admin_views.py``)는 클래스 속성만 보므로 이것을 잡지 못했다. 여기서는 실제 조립
(``create_app``)에 슈퍼유저로 로그인해 등록된 뷰 전부를 HTTP 로 연다.

DB 는 in-memory SQLite 다 — 뷰마다 행 하나를 넣고, 관리 화면의 세션 팩토리와 로그인 자격 확인을
같은 엔진으로 돌린다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.apps import Apps
from app.core.bootstrap import create_app
from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features.blog.models.models import Post
from app.features.catalog.models.models import Product
from app.features.home.models.models import UserAccessLog
from app.features.reply.models.models import Reply
from app.features.reports.models.models import SalesOrder
from app.features.sns.models.models import SnsPost
from app.features.user.models.models import User
from config import timezone_settings
from tests.admin_login import admin_login

PASSWORD = "Pages-admin-pw-123"
NOW = datetime(2026, 10, 12, 1, 2, 3, tzinfo=UTC)

#: 모델 → 시드 행 id (상세 페이지 경로).
SEED_IDS: dict[type, str] = {
    User: "u-root",
    Post: "p-1",
    Reply: "r-1",
    SnsPost: "s-1",
    Product: "pr-1",
    SalesOrder: "o-1",
    UserAccessLog: "l-1",
}


def _seed() -> list[object]:
    """뷰마다 상세 페이지를 열 행 하나 — 로그인할 슈퍼유저도 ``User`` 행이다.

    ``created_at`` 은 모두 ``NOW`` 로 고정한다 — 날짜·기간 필터가 실제로 좁히는지 볼 기준이다.
    """
    rows = _rows()
    for row in rows:
        row.created_at = NOW  # type: ignore[attr-defined]
    return rows


def _rows() -> list[object]:
    return [
        User(
            id="u-root",
            username="root",
            email="root@x.com",
            hashed_password=get_password_hasher().hash(PASSWORD),
            is_superuser=True,
        ),
        Post(id="p-1", title="제목", content="본문", author="root", author_id="u-root"),
        Reply(id="r-1", content="댓글", author="root", author_id="u-root", post_id="p-1"),
        SnsPost(id="s-1", content="글", author="root", author_id="u-root", like_count=3),
        Product(id="pr-1", sku="SKU-1", name="상품", price=Decimal("10.00"), stock=1),
        SalesOrder(
            id="o-1",
            order_no="ORD-1",
            customer="고객",
            total_amount=Decimal("10.00"),
            status="paid",
            ordered_at=NOW,
        ),
        UserAccessLog(
            id="l-1",
            ip_address="127.0.0.1",
            request_path="/health",
            request_method="GET",
            created_at=NOW,
        ),
    ]


@pytest_asyncio.fixture
async def admin_client() -> AsyncIterator[tuple[AsyncClient, list]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add_all(_seed())
        await session.commit()

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app = create_app(registry=Apps(), admin_disabled=False)
    admin = app.state.admin
    admin.authentication_backend.credentials.session_factory = factory
    for view in admin._views:
        view.session_maker = maker
        view.is_async = True
    redis = FakeRedis()
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await admin_login(client, "root", PASSWORD)
        assert login.status_code == 302
        yield client, list(admin._views)
    await redis.aclose()
    await engine.dispose()


def _filter_query(view) -> dict[str, str]:
    """뷰의 첫 필터로 거는 쿼리 하나. 연산자 필터는 그 컬럼 형식의 첫 연산을 쓴다."""
    filters = view.get_filters()
    assert filters, f"{view.identity} 에 필터가 없다 — 필터 경로를 시험할 수 없다"
    first = filters[0]
    if getattr(first, "has_operator", False):
        operation = first.get_operation_options_for_model(view.model)[0][0]
        return {first.parameter_name: "1", f"{first.parameter_name}_op": operation}
    return {first.parameter_name: "true"}


async def test_every_admin_view_lists_filters_and_shows_details(admin_client):
    client, views = admin_client
    assert len(views) >= 7, "등록된 관리 뷰가 너무 적다 — 검사가 헛통과한다"

    failures: list[str] = []
    for view in views:
        base = f"/admin/{view.identity}"
        listing = await client.get(f"{base}/list")
        filtered = await client.get(f"{base}/list", params=_filter_query(view))
        details = await client.get(f"{base}/details/{SEED_IDS[view.model]}")
        for name, response in (("list", listing), ("filter", filtered), ("details", details)):
            if response.status_code != 200:
                failures.append(f"{view.identity} {name} → {response.status_code}")

    assert not failures, failures


async def test_every_admin_view_with_created_at_lists_through_the_date_filter(admin_client):
    """``created_at`` 이 있는 모든 뷰에 날짜 필터가 있고, 연산 4종·잘못된 입력 모두 200 이다."""
    client, views = admin_client
    seeded_day = NOW.astimezone(timezone_settings.tz).date().isoformat()

    failures: list[str] = []
    for view in views:
        assert hasattr(view.model, "created_at"), f"{view.identity} 에 created_at 이 없다"
        names = [type(f).__name__ for f in view.get_filters()]
        if "LocalDateFilter" not in names:
            failures.append(f"{view.identity}: 날짜 필터 없음 {names}")
            continue
        base = f"/admin/{view.identity}/list"
        for operation, value in (
            ("on", seeded_day),
            ("from", seeded_day),
            ("before", seeded_day),
            ("between", f"{seeded_day}~{seeded_day}"),
            ("between", f"{seeded_day}~"),
            ("between", "2026-10-13~2026-10-01"),
            ("on", "not-a-date"),
        ):
            response = await client.get(
                base, params={"created_at": value, "created_at_op": operation}
            )
            if response.status_code != 200:
                failures.append(f"{view.identity} {operation}={value} → {response.status_code}")
            elif (
                'type="date" data-date-start' not in response.text
                or 'type="date" data-date-end' not in response.text
                or 'data-date-value name="created_at"' not in response.text
            ):
                failures.append(f"{view.identity}: 날짜 입력(시작·종료·합친 값)이 그려지지 않았다")

    assert not failures, failures


async def test_date_filter_narrows_the_access_log_list(admin_client):
    client, _ = admin_client
    seeded_day = NOW.astimezone(timezone_settings.tz).date().isoformat()
    base = "/admin/user-access-log/list"

    on = await client.get(base, params={"created_at": seeded_day, "created_at_op": "on"})
    before = await client.get(base, params={"created_at": seeded_day, "created_at_op": "before"})

    assert on.status_code == before.status_code == 200
    assert "details/l-1" in on.text
    assert "details/l-1" not in before.text


async def test_period_filter_narrows_every_created_at_list(admin_client):
    """기간(``between``)이 모든 created_at 목록에서 실제로 좁힌다 — 시드 날짜를 넣으면 보이고 다음 날부터면 안 보인다."""
    client, views = admin_client
    day = NOW.astimezone(timezone_settings.tz).date()
    inside = f"{day}~{day}"
    outside = f"{day + timedelta(days=1)}~"

    failures: list[str] = []
    for view in views:
        base = f"/admin/{view.identity}/list"
        detail = f"details/{SEED_IDS[view.model]}"
        hit = await client.get(base, params={"created_at": inside, "created_at_op": "between"})
        miss = await client.get(base, params={"created_at": outside, "created_at_op": "between"})
        if (hit.status_code, miss.status_code) != (200, 200):
            failures.append(f"{view.identity}: {hit.status_code}/{miss.status_code}")
        elif detail not in hit.text or detail in miss.text:
            failures.append(f"{view.identity}: 기간으로 좁혀지지 않았다")

    assert not failures, failures
