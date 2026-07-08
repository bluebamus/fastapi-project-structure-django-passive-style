"""app/utils/pagination.py 단위 테스트.

in-memory sqlite 에 User 를 적재하고 Paginator/PaginatedResponse 의
페이지 계산·정렬·필터·자동변환을 검증한다.
"""

import pytest
import pytest_asyncio
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.domains.user.models.models import User
from app.utils.pagination import PaginatedResponse, Paginator


class UserItem(BaseModel):
    id: str
    username: str


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        for i in range(25):
            s.add(User(id=f"u{i:02d}", username=f"user{i:02d}", email=f"u{i}@ex.com"))
        await s.commit()
        yield s
    await engine.dispose()


def test_create_computes_metadata():
    resp = PaginatedResponse.create(items=[1, 2], total=25, page=2, page_size=10)
    assert resp.total_pages == 3
    assert resp.has_prev is True
    assert resp.has_next is True
    assert resp.page == 2


def test_create_empty_defaults_to_one_page():
    resp = PaginatedResponse.create(items=[], total=0, page=1, page_size=10)
    assert resp.total_pages == 1
    assert resp.has_next is False
    assert resp.has_prev is False


def test_default_instance_has_initial_values():
    resp: PaginatedResponse[UserItem] = PaginatedResponse()
    assert resp.items == []
    assert resp.total == 0
    assert resp.page == 1
    assert resp.page_size == 20


async def test_paginate_first_page(session):
    paginator = Paginator(session, User, UserItem)
    result = await paginator.paginate(page=1, page_size=10, order_by="username", order_desc=False)

    assert result.total == 25
    assert result.total_pages == 3
    assert len(result.items) == 10
    assert result.has_next is True
    assert result.has_prev is False
    assert isinstance(result.items[0], UserItem)
    assert result.items[0].username == "user00"


async def test_paginate_last_page_partial(session):
    paginator = Paginator(session, User, UserItem)
    result = await paginator.paginate(page=3, page_size=10, order_by="username", order_desc=False)

    assert len(result.items) == 5
    assert result.has_next is False
    assert result.has_prev is True


async def test_paginate_page_size_capped(session):
    paginator = Paginator(session, User, UserItem, max_page_size=5)
    result = await paginator.paginate(page=1, page_size=1000)

    assert result.page_size == 5
    assert len(result.items) == 5


async def test_paginate_filter(session):
    paginator = Paginator(session, User, UserItem)
    result = await paginator.paginate(filters={"username": "user07"})

    assert result.total == 1
    assert result.items[0].username == "user07"


async def test_paginate_transform_fn(session):
    paginator = Paginator(session, User, UserItem)
    result = await paginator.paginate(
        page=1,
        page_size=3,
        order_by="username",
        order_desc=False,
        transform_fn=lambda u: UserItem(id=u.id, username=u.username.upper()),
    )

    assert result.items[0].username == "USER00"


@pytest.mark.parametrize("page", [0, -5])
async def test_paginate_page_below_one_is_clamped(session, page):
    paginator = Paginator(session, User, UserItem)
    result = await paginator.paginate(page=page, page_size=10)
    assert result.page == 1
