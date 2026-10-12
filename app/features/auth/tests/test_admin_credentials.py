"""``UserAdminCredentials`` — /admin 로그인의 사용자 DB 쪽 판정 (admin-login ADR-002).

활성 슈퍼유저만 관리자다. 비밀번호 확인·bcrypt → Argon2 재해시는 API 로그인과 같은
``verify_credentials`` 를 쓴다. 세션 팩토리는 in-memory SQLite 로 바꿔 끼운다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import bcrypt
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features.auth.admin_credentials import UserAdminCredentials, default_admin_credentials
from app.features.user.models.models import User

PASSWORD = "admin-pw-123"


@pytest_asyncio.fixture
async def maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def credentials(maker) -> UserAdminCredentials:
    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    hasher = get_password_hasher()
    async with maker() as session:
        for name, superuser, active in (
            ("root", True, True),
            ("bob", False, True),
            ("gone", True, False),
        ):
            session.add(
                User(
                    id=f"u-{name}",
                    username=name,
                    email=f"{name}@x.com",
                    hashed_password=hasher.hash(PASSWORD),
                    is_superuser=superuser,
                    is_active=active,
                )
            )
        await session.commit()
    return UserAdminCredentials(factory, hasher)


async def test_active_superuser_with_the_right_password_is_admin(credentials):
    assert await credentials.verify("root", PASSWORD) == "u-root"


async def test_wrong_password_unknown_user_non_superuser_and_inactive_are_all_none(credentials):
    results = [
        await credentials.verify("root", "wrong-password"),
        await credentials.verify("nobody", PASSWORD),
        await credentials.verify("bob", PASSWORD),
        await credentials.verify("gone", PASSWORD),
    ]

    assert results == [None, None, None, None]


async def test_is_admin_follows_the_database(credentials, maker):
    assert await credentials.is_admin("u-root") is True
    assert await credentials.is_admin("u-bob") is False
    assert await credentials.is_admin("u-gone") is False
    assert await credentials.is_admin("u-missing") is False

    async with maker() as session:
        await session.execute(update(User).where(User.id == "u-root").values(is_superuser=False))
        await session.commit()

    assert await credentials.is_admin("u-root") is False, "강등이 바로 반영되지 않았다"


async def test_legacy_bcrypt_hash_is_rehashed_and_committed(credentials, maker):
    legacy = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    async with maker() as session:
        await session.execute(
            update(User).where(User.id == "u-root").values(hashed_password=legacy)
        )
        await session.commit()

    assert await credentials.verify("root", PASSWORD) == "u-root"

    async with maker() as session:
        stored = await session.scalar(select(User.hashed_password).where(User.id == "u-root"))
    assert stored is not None and stored.startswith("$argon2"), "재해시가 저장되지 않았다"


def test_default_assembly_uses_the_background_session_and_the_shared_hasher():
    from app.core.db.session import background_session

    built = default_admin_credentials()

    assert built.session_factory is background_session
    assert built.password_hasher is get_password_hasher()
