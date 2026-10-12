"""고정 창 레이트 리밋 — Redis (service-hardening ADR-016).

창마다 키 하나를 ``INCR`` 하고, 창의 첫 hit 에만 만료를 건다(``EXPIRE NX``). 이후 hit 이
만료를 늘리면 창이 미끄러져 공격자가 끝없이 막히는 대신 정상 사용자도 풀리지 않는다 —
고정 창은 첫 hit 시각으로 고정한다. 세 명령을 MULTI 로 묶어 INCR 만 되고 만료가 빠지는
(영원히 막히는) 키가 생기지 않게 한다.

ponytail: 고정 창은 창 경계에서 최대 2배까지 몰아칠 수 있다. 막아야 하면 슬라이딩 로그
(ZSET)나 GCRA 로 바꾼다.
"""

from __future__ import annotations

from typing import NamedTuple

from redis.asyncio import Redis

_KEY_PREFIX = "rl:"


class RateLimitResult(NamedTuple):
    """판정 결과 — 허용 여부와 창이 끝날 때까지 남은 초(거부 시 ``Retry-After``)."""

    allowed: bool
    retry_after: int


class RateLimiter:
    """키별 고정 창 카운터.

    Args:
        redis: lifespan 이 소유한 클라이언트(``get_redis`` 로 주입).
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit: int, window: int) -> RateLimitResult:
        """시도 하나를 센다. 창 안의 시도 수가 ``limit`` 을 넘으면 거부한다."""
        name = _KEY_PREFIX + key
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(name)
            pipe.expire(name, window, nx=True)
            pipe.ttl(name)
            count, _, ttl = await pipe.execute()
        # TTL 이 양수가 아니면(만료 직전 경합 등) 창 전체를 기다리게 한다.
        retry_after = ttl if ttl > 0 else window
        return RateLimitResult(count <= limit, retry_after)

    async def reset(self, key: str) -> None:
        """카운터를 지운다(예: 로그인 성공 시 ip+username 카운터)."""
        await self._redis.delete(_KEY_PREFIX + key)
