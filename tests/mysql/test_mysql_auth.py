"""MySQL 8 기본 인증(``caching_sha2_password``)으로 앱 드라이버(aiomysql)가 접속한다.

막 만든 사용자라 서버 인증 캐시가 비어 있다 — 비 TLS 연결의 첫 접속은 RSA 공개키 교환(전체 인증)을 탄다.
``aiomysql[rsa]``(cryptography)가 빠지면 여기서 "'cryptography' package is required" 로 실패한다.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def test_fresh_caching_sha2_user_connects_with_app_driver(
    mysql_server_url: URL, readonly_user_url: URL
):
    admin = create_async_engine(mysql_server_url, poolclass=NullPool)
    user_engine = create_async_engine(readonly_user_url, poolclass=NullPool)
    try:
        async with admin.connect() as conn:
            plugin = (
                await conn.execute(
                    text("SELECT plugin FROM mysql.user WHERE user = :u"),
                    {"u": readonly_user_url.username},
                )
            ).scalar_one()
        async with user_engine.connect() as conn:
            current = (await conn.execute(text("SELECT CURRENT_USER()"))).scalar_one()

        assert plugin == "caching_sha2_password"
        assert current.startswith(f"{readonly_user_url.username}@")
    finally:
        await user_engine.dispose()
        await admin.dispose()
