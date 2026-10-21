"""replica 연결 오류 → primary 로 한 번 재시도 (integration-e2e F-005 · 사용자 결정 2 · ADR-010).

읽기 전용 세션의 읽기가 replica 에 **연결하지 못하면**(접속 거부·연결 끊김·타임아웃) 같은 구문을 primary 로 한 번
다시 실행하고 WARNING 을 남긴다. 쿼리 자체의 오류(없는 테이블 등)는 재시도하지 않는다. 쓰기가 섞일 수 있는 일반
(라우팅) 세션도 재시도하지 않는다.

죽은 replica 는 **닫힌 로컬 포트**(127.0.0.1:1)의 MySQL URL 이다 — 어디에도 실제로 접속하지 않는다.
"""

from __future__ import annotations

import logging

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db.router import DatabaseRouter, create_routing_sessionmaker, mark_read_only
from tests.core.test_db_router import Probe, _make_engine, _origins

DEAD_REPLICA_URL = "mysql+aiomysql://nobody:nothing@127.0.0.1:1/nowhere"


def _dead_replica():
    return create_async_engine(DEAD_REPLICA_URL, connect_args={"connect_timeout": 2})


async def test_read_only_session_falls_back_to_primary_when_replica_is_unreachable(caplog):
    writer = await _make_engine("writer")
    replica = _dead_replica()
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[replica]))
    try:
        async with maker() as session:
            mark_read_only(session)
            with caplog.at_level(logging.WARNING):
                assert await _origins(session) == ["writer"]
                # 같은 세션의 다음 읽기도 primary 다 — 죽은 replica 를 다시 두드리지 않는다.
                assert (await session.execute(select(Probe.origin))).scalar_one() == "writer"
        warnings = [r for r in caplog.records if "replica" in r.getMessage()]
        assert len(warnings) == 1 and warnings[0].levelno == logging.WARNING
        assert (
            "nothing" not in warnings[0].getMessage() and "nobody" not in warnings[0].getMessage()
        )
    finally:
        await writer.dispose()
        await replica.dispose()


async def test_routed_session_does_not_retry_on_primary():
    """읽기 전용이 아닌 세션은 쓰기와 같은 트랜잭션일 수 있다 — 재시도 대상이 아니다."""
    writer = await _make_engine("writer")
    replica = _dead_replica()
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[replica]))
    try:
        async with maker() as session:
            with pytest.raises(OperationalError):
                await _origins(session)
    finally:
        await writer.dispose()
        await replica.dispose()


async def test_query_error_on_replica_is_not_retried():
    """연결은 됐는데 쿼리가 실패하면(여기서는 replica 에 테이블이 없다) primary 로 숨기지 않는다."""
    writer = await _make_engine("writer")
    replica = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[replica]))
    try:
        async with maker() as session:
            mark_read_only(session)
            with pytest.raises(OperationalError):
                await _origins(session)
    finally:
        await writer.dispose()
        await replica.dispose()


async def test_single_database_has_no_fallback(caplog):
    """replica 가 없는 구성 — 읽기도 writer 로 가고, writer 오류는 재시도·경고 없이 그대로 올라간다."""
    writer = _dead_replica()
    maker = create_routing_sessionmaker(DatabaseRouter(writer=writer, readers=[]))
    try:
        async with maker() as session:
            mark_read_only(session)
            with caplog.at_level(logging.WARNING), pytest.raises(OperationalError):
                await _origins(session)
        assert not [r for r in caplog.records if "replica" in r.getMessage()]
    finally:
        await writer.dispose()
