"""쓰기 핸들러는 응답 DTO 를 **검증한 뒤** 커밋한다 (단일 트랜잭션 규칙).

순서가 반대(commit → 검증)이면 DTO 검증이 실패했을 때 클라이언트는 500 을 받는데
데이터는 이미 커밋돼 남는다. "실패한 요청은 아무것도 남기지 않는다"가 깨진다.

모든 기능 앱의 생성·수정 핸들러를 대상으로, 라우터 모듈이 쓰는 응답 DTO 를
``model_validate`` 가 예외를 던지는 클래스로 바꿔 끼운 뒤 다음을 확인한다.

1. 응답은 500
2. 커밋 0회
3. DB 는 요청 전과 같다(생성: 행 없음, 수정: 값 그대로)

``response_model`` 은 데코레이터 시점에 이미 원래 클래스로 고정되므로 OpenAPI 는
바뀌지 않는다 — 바꿔 끼우는 것은 핸들러 본문이 참조하는 모듈 전역 이름뿐이다.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.blog.models.models import Post
from app.features.catalog.models.models import Product
from app.features.reply.models.models import Reply
from app.features.sns.models.models import SnsPost
from app.features.user.models.models import User
from main import app


@dataclass(frozen=True)
class WriteCase:
    """생성(``update is None``) 또는 생성 후 수정 한 건."""

    name: str
    module: str
    dto: str
    collection: str
    create: dict[str, Any]
    model: type
    update: dict[str, Any] | None = None


_BLOG = {"title": "제목", "content": "본문", "author": "kim"}
_REPLY = {"content": "댓글", "author": "lee", "post_id": "p1"}
_SNS = {"content": "피드", "author": "park"}
_USER = {"username": "alice", "email": "alice@example.com"}
_PRODUCT = {"sku": "SKU-DTO", "name": "상품", "price": "1000.00", "stock": 1}

CASES = [
    WriteCase(
        "blog-create",
        "app.features.blog.api.routers.v1.blog",
        "PostResponse",
        "/api/v1/blog/posts",
        _BLOG,
        Post,
    ),
    WriteCase(
        "blog-update",
        "app.features.blog.api.routers.v1.blog",
        "PostResponse",
        "/api/v1/blog/posts",
        _BLOG,
        Post,
        {"title": "바뀐 제목"},
    ),
    WriteCase(
        "reply-create",
        "app.features.reply.api.routers.v1.reply",
        "ReplyResponse",
        "/api/v1/reply/replies",
        _REPLY,
        Reply,
    ),
    WriteCase(
        "reply-update",
        "app.features.reply.api.routers.v1.reply",
        "ReplyResponse",
        "/api/v1/reply/replies",
        _REPLY,
        Reply,
        {"content": "바뀐 댓글"},
    ),
    WriteCase(
        "sns-create",
        "app.features.sns.api.routers.v1.sns",
        "SnsPostResponse",
        "/api/v1/sns/posts",
        _SNS,
        SnsPost,
    ),
    WriteCase(
        "sns-update",
        "app.features.sns.api.routers.v1.sns",
        "SnsPostResponse",
        "/api/v1/sns/posts",
        _SNS,
        SnsPost,
        {"content": "바뀐 피드"},
    ),
    WriteCase(
        "user-create",
        "app.features.user.api.routers.v1.user",
        "UserResponse",
        "/api/v1/user/users",
        _USER,
        User,
    ),
    WriteCase(
        "user-update",
        "app.features.user.api.routers.v1.user",
        "UserResponse",
        "/api/v1/user/users",
        _USER,
        User,
        {"is_active": False},
    ),
    WriteCase(
        "catalog-create",
        "app.features.catalog.api.routers.v1.products",
        "ProductResponse",
        "/api/v1/catalog/products",
        _PRODUCT,
        Product,
    ),
    WriteCase(
        "catalog-update",
        "app.features.catalog.api.routers.v1.products",
        "ProductResponse",
        "/api/v1/catalog/products",
        _PRODUCT,
        Product,
        {"name": "바뀐 상품"},
    ),
    WriteCase(
        "auth-register",
        "app.features.auth.api.routers.v1.auth",
        "AuthenticatedUserResponse",
        "/api/v1/auth/register",
        {"username": "bob", "email": "bob@example.com", "password": "secret-pw-1234"},
        User,
    ),
]


@pytest_asyncio.fixture
async def counting_client():
    """커밋 횟수를 세는 in-memory DB 클라이언트와 세션 팩토리."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    calls = {"commit": 0}

    async def _override_get_session():
        async with maker() as session:
            original_commit = session.commit

            async def _counting_commit(*args, **kwargs):
                calls["commit"] += 1
                return await original_commit(*args, **kwargs)

            session.commit = _counting_commit  # type: ignore[method-assign]
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_writer_db_session] = _override_get_session
    app.dependency_overrides[get_read_only_db_session] = _override_get_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, calls, maker
    app.dependency_overrides.clear()
    await engine.dispose()


def _broken_dto(original: type) -> type:
    class _Broken(original):  # type: ignore[misc, valid-type]
        @classmethod
        def model_validate(cls, *args: Any, **kwargs: Any) -> Any:
            raise ValueError("injected response DTO failure")

    return _Broken


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
async def test_dto_failure_leaves_nothing_committed(counting_client, monkeypatch, case: WriteCase):
    client, calls, maker = counting_client
    module = importlib.import_module(case.module)

    target_url = case.collection
    created: dict[str, Any] | None = None
    if case.update is not None:
        resp = await client.post(case.collection, json=case.create)
        assert resp.status_code == 201, resp.text
        created = resp.json()
        target_url = f"{case.collection}/{created['id']}"
    calls["commit"] = 0

    monkeypatch.setattr(module, case.dto, _broken_dto(getattr(module, case.dto)))
    if case.update is None:
        resp = await client.post(target_url, json=case.create)
    else:
        resp = await client.patch(target_url, json=case.update)

    assert resp.status_code == 500, resp.text
    assert calls["commit"] == 0, f"DTO 검증 실패인데 {calls['commit']}회 커밋했다"

    async with maker() as session:
        if created is None:
            count = await session.scalar(select(func.count()).select_from(case.model))
            assert count == 0, "DTO 검증 실패한 생성 요청의 행이 DB 에 남았다"
        else:
            row = await session.get(case.model, created["id"])
            assert row is not None
            for key in case.update or {}:
                assert getattr(row, key) == created[key], f"{key} 가 실패한 요청으로 바뀌었다"
