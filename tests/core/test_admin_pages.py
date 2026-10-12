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
from datetime import UTC, datetime
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
    """뷰마다 상세 페이지를 열 행 하나 — 로그인할 슈퍼유저도 ``User`` 행이다."""
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
            id="l-1", ip_address="127.0.0.1", request_path="/health", request_method="GET"
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
        login = await client.post("/admin/login", data={"username": "root", "password": PASSWORD})
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
