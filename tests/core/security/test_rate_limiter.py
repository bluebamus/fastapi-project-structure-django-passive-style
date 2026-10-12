"""RateLimiter — Redis 고정 창 (service-hardening ADR-016). 실물 클래스를 fakeredis 로 시험한다."""

import asyncio

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.security import RateLimiter, RateLimitResult


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def limiter(redis) -> RateLimiter:
    return RateLimiter(redis)


async def test_allows_up_to_the_limit_then_denies(limiter):
    results = [await limiter.hit("k", limit=3, window=60) for _ in range(4)]

    assert [r.allowed for r in results] == [True, True, True, False]


async def test_denial_reports_the_remaining_window(limiter):
    for _ in range(2):
        result = await limiter.hit("k", limit=1, window=60)

    assert isinstance(result, RateLimitResult)
    assert result.allowed is False
    assert 55 <= result.retry_after <= 60


async def test_first_hit_sets_the_window_expiry(limiter, redis):
    await limiter.hit("k", limit=5, window=60)

    assert 0 < await redis.ttl("rl:k") <= 60


async def test_later_hits_do_not_extend_the_window(limiter, redis):
    """EXPIRE NX — 창은 첫 hit 시각으로 고정된다(미끄러지지 않는다)."""
    await limiter.hit("k", limit=5, window=60)
    await redis.expire("rl:k", 5)  # 창의 끝에 가까워진 상태를 만든다

    result = await limiter.hit("k", limit=5, window=60)

    assert await redis.ttl("rl:k") <= 5
    assert result.retry_after <= 5


async def test_counter_resets_after_the_window_expires(limiter, redis):
    for _ in range(2):
        await limiter.hit("k", limit=1, window=60)
    await redis.pexpire("rl:k", 1)
    await asyncio.sleep(0.02)

    assert (await limiter.hit("k", limit=1, window=60)).allowed is True


async def test_reset_clears_the_counter(limiter):
    for _ in range(2):
        await limiter.hit("k", limit=1, window=60)

    await limiter.reset("k")

    assert (await limiter.hit("k", limit=1, window=60)).allowed is True


async def test_keys_are_independent(limiter):
    await limiter.hit("a", limit=1, window=60)

    assert (await limiter.hit("b", limit=1, window=60)).allowed is True
