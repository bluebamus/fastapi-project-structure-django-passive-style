"""Redis 클라이언트 주입 지점 (service-hardening ADR-011).

Redis 는 필수다. 클라이언트는 lifespan(:mod:`app.core.resources`)이 기동 시 ping 으로
검증해 ``app.state.redis`` 에 두고 종료 시 닫는다. 요청 코드는 이 provider 하나로만
꺼낸다 — 기능이 ``Redis.from_url`` 을 직접 만들면 연결 풀이 기능 수만큼 생기고 종료
시 아무도 닫지 않는다. 테스트는 ``app.state.redis`` 에 가짜(fakeredis 등)를 넣거나
``app.dependency_overrides[get_redis]`` 로 바꾼다.

최소 버전은 :data:`REDIS_MIN_VERSION` 하나이고, lifespan 이 연결 직후
:func:`ensure_redis_version` 으로 확인한다(log-redaction-fixes ADR-004).
"""

from __future__ import annotations

import asyncio

from fastapi import Request
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.core.exception import ServiceUnavailableException
from app.utils.logs import get_logger

logger = get_logger("app.core.redis")

#: 지원하는 최소 Redis 서버 버전 = 코드가 쓰는 명령의 요구 버전 중 최댓값.
#:
#:   ``EXPIRE key seconds NX``  (``security/rate_limit.py``)     → 7.0   ← 이것이 최소 버전을 정한다
#:   ``GETDEL``                  (``security/refresh_store.py``)  → 6.2
#:   ``SET … NX EX`` · ``INCR`` · ``TTL`` · ``SADD`` · ``MULTI``  → 2.6.12 이하
#:
#: 6.x 서버는 ``EXPIRE … NX`` 를 문법 오류로 거부해 로그인·가입 레이트 리밋이 첫 요청부터
#: 500 이 된다. 명령을 더하면 이 표와 값을 같이 고친다 —
#: ``tests/core/test_redis_version.py`` 가 소스의 명령과 이 값을 대조한다.
REDIS_MIN_VERSION: tuple[int, int] = (7, 0)


class UnsupportedRedisVersion(RuntimeError):
    """Redis 서버가 :data:`REDIS_MIN_VERSION` 보다 낮다 — 기동을 멈춘다."""


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


def _min_version_text() -> str:
    return ".".join(str(part) for part in REDIS_MIN_VERSION)


async def ensure_redis_version(client: Redis) -> None:
    """``INFO server`` 의 ``redis_version`` 이 최소 버전 미만이면 기동을 멈춘다.

    ``INFO`` 를 막아 둔 관리형 Redis(명령 이름 변경·ACL)나 버전을 알려 주지 않는 서버는
    판정할 수 없으므로 WARNING 만 남기고 계속한다 — Redis 필수 정책이 막는 것은 "연결이
    안 되는 Redis" 이고, 이 확인은 그 위의 안전망이다.

    Raises:
        UnsupportedRedisVersion: 보고된 버전이 :data:`REDIS_MIN_VERSION` 보다 낮다.
    """
    try:
        info = await client.info("server")
    except ResponseError as exc:
        logger.warning(
            "[startup] Redis 버전 확인 생략 — INFO 를 쓸 수 없다(%s). %s 이상인지 직접 확인하라",
            type(exc).__name__,
            _min_version_text(),
        )
        return
    reported = str(info.get("redis_version", ""))
    try:
        version = tuple(int(part) for part in reported.split(".")[:2])
    except ValueError:
        logger.warning(
            "[startup] Redis 버전 확인 생략 — 버전을 읽지 못했다(%r). %s 이상인지 직접 확인하라",
            reported,
            _min_version_text(),
        )
        return
    if version < REDIS_MIN_VERSION:
        raise UnsupportedRedisVersion(
            f"Redis {reported} 는 지원하지 않는다 — {_min_version_text()} 이상이 필요하다"
            " (레이트 리밋이 EXPIRE NX 를 쓴다)"
        )
    logger.info("[startup] Redis 버전 %s 확인", reported)
