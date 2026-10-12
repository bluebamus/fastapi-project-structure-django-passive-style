"""Redis 클라이언트 주입 지점 (service-hardening ADR-011).

Redis 는 필수다. 클라이언트는 lifespan(:mod:`app.core.resources`)이 기동 시 ping 으로
검증해 ``app.state.redis`` 에 두고 종료 시 닫는다. 요청 코드는 이 provider 하나로만
꺼낸다 — 기능이 ``Redis.from_url`` 을 직접 만들면 연결 풀이 기능 수만큼 생기고 종료
시 아무도 닫지 않는다. 테스트는 ``app.state.redis`` 에 가짜(fakeredis 등)를 넣거나
``app.dependency_overrides[get_redis]`` 로 바꾼다.
"""

from __future__ import annotations

import asyncio

from fastapi import Request
from redis.asyncio import Redis

from app.core.exception import ServiceUnavailableException


def get_redis(request: Request) -> Redis:
    """lifespan 이 소유한 Redis 클라이언트를 돌려준다.

    Raises:
        ServiceUnavailableException: lifespan 밖(기동 전·종료 후)이라 클라이언트가 없다.
    """
    client: Redis | None = getattr(request.app.state, "redis", None)
    if client is None:
        raise ServiceUnavailableException("Redis 를 사용할 수 없습니다.")
    return client


async def ping_redis(client: Redis, timeout: float) -> None:
    """``timeout`` 안에 ``PING`` 이 돌아오지 않으면 ``TimeoutError`` (readiness 용)."""
    async with asyncio.timeout(timeout):
        await client.ping()
