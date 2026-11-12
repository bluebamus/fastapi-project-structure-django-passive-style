"""MySQL 전용 검증의 픽스처 — **CI 전용**(``.github/workflows/ci.yml`` 의 ``mysql`` 잡).

평소 ``pytest`` 는 이 폴더를 수집하지 않는다(pyproject ``norecursedirs``). 경로를 직접 줄 때만 돈다::

    MYSQL_TEST_URL=mysql+aiomysql://root:<pw>@<host>:<port> pytest tests/mysql

``MYSQL_TEST_URL`` 은 **자기 소유의 빈 MySQL 서버**여야 한다 — 테스트마다 ``t_<hex>`` DB·사용자를
만들고 지우므로 ``CREATE DATABASE``·``CREATE USER`` 권한이 필요하다. 변수가 없으면 skip 이 아니라
**실패**한다(기본 접속 대상을 두지 않는다 — 남의 서버에 붙지 않게).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

ENV_NAME = "MYSQL_TEST_URL"


@pytest.fixture(scope="session")
def mysql_server_url() -> URL:
    """``MYSQL_TEST_URL`` (DB 이름 없이 서버만). 없거나 MySQL 이 아니면 연결 전에 실패한다."""
    raw = os.environ.get(ENV_NAME, "").strip()
    if not raw:
        pytest.fail(
            f"{ENV_NAME} 가 없습니다 — MySQL 테스트는 CI 전용입니다. 로컬에서 돌리려면 자기 소유의 빈 "
            f"MySQL 을 {ENV_NAME}=mysql+aiomysql://user:pw@host:port 로 주세요.",
            pytrace=False,
        )
    url = make_url(raw)
    if url.get_backend_name() != "mysql":
        pytest.fail(f"{ENV_NAME} 는 mysql URL 이어야 합니다: {url.drivername}", pytrace=False)
    return url.set(drivername="mysql+aiomysql", database=None)


def server_engine(url: URL) -> AsyncEngine:
    return create_async_engine(url, poolclass=NullPool)


@pytest.fixture
async def mysql_url(mysql_server_url: URL) -> AsyncIterator[URL]:
    """테스트 하나 전용의 빈 DB(``utf8mb4``) URL — 끝나면 DB 를 지운다."""
    name = f"t_{uuid.uuid4().hex[:16]}"
    admin = server_engine(mysql_server_url)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4"))
        yield mysql_server_url.set(database=name)
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS `{name}`"))
        await admin.dispose()


@pytest.fixture
async def mysql_engine(mysql_url: URL) -> AsyncIterator[AsyncEngine]:
    """앱 엔진과 같은 드라이버·charset 의 엔진(테스트 DB)."""
    engine = create_async_engine(mysql_url, poolclass=NullPool, connect_args={"charset": "utf8mb4"})
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def readonly_user_url(mysql_server_url: URL, mysql_url: URL) -> AsyncIterator[URL]:
    """테스트 DB 에 ``SELECT`` 만 가진 새 사용자(``caching_sha2_password``)의 URL — 끝나면 지운다.

    사용자를 매번 새로 만드는 이유: 서버의 인증 캐시가 비어 있어 첫 접속이 **전체 인증**(비 TLS 면 RSA)을 탄다.
    """
    user, password = f"ro_{uuid.uuid4().hex[:12]}", uuid.uuid4().hex
    admin = server_engine(mysql_server_url)
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    f"CREATE USER '{user}'@'%' IDENTIFIED WITH caching_sha2_password BY '{password}'"
                )
            )
            await conn.execute(text(f"GRANT SELECT ON `{mysql_url.database}`.* TO '{user}'@'%'"))
        yield mysql_url.set(username=user, password=password)
    finally:
        async with admin.begin() as conn:
            await conn.execute(text(f"DROP USER IF EXISTS '{user}'@'%'"))
        await admin.dispose()
