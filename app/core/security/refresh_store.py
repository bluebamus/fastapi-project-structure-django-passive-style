"""refresh 토큰 회전 기록 — Redis (service-hardening ADR-015).

키:
    - ``auth:rt:{jti}`` → ``{"sub", "fam"}``: 아직 쓰지 않은 refresh 토큰. TTL = refresh 수명.
    - ``auth:user:{sub}:fams``: 사용자가 가진 family 집합(사용자 단위 폐기용). TTL = refresh 수명.
    - ``auth:fam:{fam}:revoked``: 폐기된 family 표시. TTL = refresh 수명(그 family 의 어떤
      토큰도 그보다 오래 살지 못한다).

회전은 ``GETDEL`` 하나로 jti 를 소비한다 — 두 요청이 같은 토큰으로 경쟁해도 한쪽만 값을
받는다. 값이 없으면 이미 쓴 토큰의 **재사용**이므로 호출자가 family 를 폐기한다.
"""

from __future__ import annotations

import json

from redis.asyncio import Redis


class RefreshTokenStore:
    """refresh 토큰의 1회 사용·family 폐기를 기록한다.

    Args:
        redis: lifespan 이 소유한 클라이언트(``get_redis`` 로 주입).
        ttl_seconds: refresh 토큰 수명(초). 모든 키의 TTL 이다.
    """

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def register(self, jti: str, sub: str, fam: str) -> None:
        """새로 발급한 refresh 토큰을 기록한다(토큰 기록과 사용자 family 집합을 한 트랜잭션으로)."""
        user_fams = _user_fams_key(sub)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(_token_key(jti), json.dumps({"sub": sub, "fam": fam}), ex=self._ttl)
            pipe.sadd(user_fams, fam)
            pipe.expire(user_fams, self._ttl)
            await pipe.execute()

    async def consume(self, jti: str) -> bool:
        """jti 를 소비한다. 처음 쓰는 토큰이면 True, 이미 썼거나 모르는 토큰이면 False."""
        return await self._redis.getdel(_token_key(jti)) is not None

    async def revoke_family(self, fam: str) -> None:
        """family 를 폐기한다(멱등). 그 family 의 refresh 토큰은 더 이상 회전되지 않는다."""
        await self._redis.set(_revoked_key(fam), "1", ex=self._ttl)

    async def is_family_revoked(self, fam: str) -> bool:
        """family 가 폐기됐는지."""
        return bool(await self._redis.exists(_revoked_key(fam)))

    async def revoke_user(self, sub: str) -> None:
        """사용자의 모든 family 를 폐기한다(비활성화·삭제 시)."""
        user_fams = _user_fams_key(sub)
        # redis-py 의 타입 표기가 동기·비동기 반환을 합쳐 둔다 — 비동기 클라이언트라 awaitable 이다.
        fams = await self._redis.smembers(user_fams)  # type: ignore[misc]
        async with self._redis.pipeline(transaction=True) as pipe:
            for fam in fams:
                name = fam.decode() if isinstance(fam, bytes) else fam
                pipe.set(_revoked_key(name), "1", ex=self._ttl)
            pipe.delete(user_fams)
            await pipe.execute()


def _token_key(jti: str) -> str:
    return f"auth:rt:{jti}"


def _user_fams_key(sub: str) -> str:
    return f"auth:user:{sub}:fams"


def _revoked_key(fam: str) -> str:
    return f"auth:fam:{fam}:revoked"
