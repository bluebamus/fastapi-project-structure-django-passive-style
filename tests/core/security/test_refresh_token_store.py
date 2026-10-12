"""RefreshTokenStore — 1회 소비·family 폐기 (service-hardening ADR-015). 실물 클래스를 fakeredis 로 시험한다."""

import json

import pytest
from fakeredis.aioredis import FakeRedis

from app.core.security import RefreshTokenStore

TTL = 600


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def store(redis) -> RefreshTokenStore:
    return RefreshTokenStore(redis, ttl_seconds=TTL)


async def test_register_records_token_and_user_family_with_ttl(store, redis):
    await store.register("jti-1", "user-1", "fam-1")

    assert json.loads(await redis.get("auth:rt:jti-1")) == {"sub": "user-1", "fam": "fam-1"}
    assert await redis.smembers("auth:user:user-1:fams") == {b"fam-1"}
    assert 0 < await redis.ttl("auth:rt:jti-1") <= TTL
    assert 0 < await redis.ttl("auth:user:user-1:fams") <= TTL


async def test_consume_succeeds_only_once(store):
    await store.register("jti-1", "user-1", "fam-1")

    assert await store.consume("jti-1") is True
    assert await store.consume("jti-1") is False


async def test_unknown_jti_is_not_consumable(store):
    assert await store.consume("never-issued") is False


async def test_revoke_family_marks_it_with_ttl(store, redis):
    assert await store.is_family_revoked("fam-1") is False

    await store.revoke_family("fam-1")
    await store.revoke_family("fam-1")  # 멱등

    assert await store.is_family_revoked("fam-1") is True
    assert 0 < await redis.ttl("auth:fam:fam-1:revoked") <= TTL


async def test_revoke_user_revokes_every_family_of_that_user_only(store, redis):
    await store.register("j1", "user-1", "fam-a")
    await store.register("j2", "user-1", "fam-b")
    await store.register("j3", "user-2", "fam-c")

    await store.revoke_user("user-1")

    assert await store.is_family_revoked("fam-a") is True
    assert await store.is_family_revoked("fam-b") is True
    assert await store.is_family_revoked("fam-c") is False
    assert await redis.exists("auth:user:user-1:fams") == 0


async def test_revoke_user_without_families_is_a_no_op(store):
    await store.revoke_user("nobody")
