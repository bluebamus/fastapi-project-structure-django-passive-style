"""비동기 runtime 과 자원 수명 계약.

여기서 보는 것은 "기능이 동작하는가"가 아니라 **자원이 반드시 닫히는가**다.
이 구간의 결함은 개발 중에는 보이지 않고 운영에서 커넥션 누수·좀비 프로세스로만
드러난다 — 그래서 실행 순서와 예산을 계약으로 못 박는다.
"""

from __future__ import annotations

import logging

import pytest

from app.core.db import session as db_session


# =============================================================================
# 커넥션 풀 예산
# =============================================================================
def test_total_connection_estimate_counts_every_engine():
    """총 연결 수 계산이 writer·reader·background 와 프로세스 수를 모두 반영한다."""
    from config import DatabaseSettings

    settings = DatabaseSettings(
        DB_POOL_SIZE=10,
        DB_MAX_OVERFLOW=5,
        DB_BACKGROUND_POOL_SIZE=2,
        DB_BACKGROUND_MAX_OVERFLOW=1,
        DB_WORKER_PROCESSES=4,
    )

    # (10+5) x 1 엔진 + (2+1) = 18, x 4 프로세스 = 72
    assert settings.max_total_connections == 72


def test_pool_settings_that_exceed_the_server_limit_are_rejected():
    """상한을 넘는 풀 설정은 기동 시점에 막는다.

    이 초과는 평소엔 안 보이다가 트래픽이 몰릴 때만 "Too many connections" 로
    터진다 — 가장 나쁜 시점에 드러나는 종류의 설정 오류다.
    """
    from pydantic import ValidationError

    from config import DatabaseSettings

    with pytest.raises(ValidationError, match="DB_MAX_SERVER_CONNECTIONS"):
        DatabaseSettings(
            DB_POOL_SIZE=50,
            DB_MAX_OVERFLOW=50,
            DB_WORKER_PROCESSES=8,
            DB_MAX_SERVER_CONNECTIONS=100,
        )


def test_unknown_server_limit_skips_validation():
    """서버 상한을 모르면 검증하지 않는다 — 모르는 값을 지어내지 않는다."""
    from config import DatabaseSettings

    settings = DatabaseSettings(
        DB_POOL_SIZE=50,
        DB_MAX_OVERFLOW=50,
        DB_BACKGROUND_POOL_SIZE=10,
        DB_BACKGROUND_MAX_OVERFLOW=10,
        DB_WORKER_PROCESSES=8,
        DB_MAX_SERVER_CONNECTIONS=0,
    )
    # ((50+50) x 1 엔진 + (10+10)) x 8 프로세스 = 960. 상한을 모르면 막지 않는다.
    assert settings.max_total_connections == 960


def test_engines_use_the_configured_pool_size():
    """하드코딩이 아니라 설정을 실제로 반영한다."""
    from config import db_settings

    assert db_session.engine.pool.size() == db_settings.DB_POOL_SIZE


# =============================================================================
# dispose_engine — 한 엔진이 실패해도 나머지는 회수한다
# =============================================================================
class _FakeEngine:
    """dispose 호출 여부만 기록하는 엔진 대역."""

    def __init__(self, name: str, disposed: list[str], *, fail: bool = False) -> None:
        self.name = name
        self.disposed = disposed
        self.fail = fail

    async def dispose(self) -> None:
        self.disposed.append(self.name)
        if self.fail:
            raise RuntimeError("dispose 실패(모의) dsn=mysql://u:hunter2@host/db")


async def test_dispose_engine_reclaims_every_engine_even_if_one_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """writer dispose 가 터져도 replica·background 까지 회수한다.

    앞의 dispose 에서 멈추면 뒤의 풀이 그대로 남아 DB 쪽에 좀비 커넥션이 된다.
    증상은 한참 뒤 "커넥션 소진"으로만 나타나 원인 추적이 어렵다.
    """
    disposed: list[str] = []
    monkeypatch.setattr(db_session, "engine", _FakeEngine("writer", disposed, fail=True))
    monkeypatch.setattr(db_session, "read_engines", [_FakeEngine("reader#0", disposed)])
    monkeypatch.setattr(db_session, "background_engine", _FakeEngine("background", disposed))

    with caplog.at_level(logging.ERROR, logger="database"):
        await db_session.dispose_engine()

    assert sorted(disposed) == ["background", "reader#0", "writer"]

    text = caplog.text
    assert "writer" in text, "실패한 엔진 이름이 없으면 어느 풀이 남았는지 알 수 없다"
    assert "RuntimeError" in text
    assert "hunter2" not in text, "예외 원문에 실린 DSN 자격증명이 로그로 새어 나갔다"


# =============================================================================
# 세션 Dependency — 예외 경로에서 ROLLBACK 은 정확히 1회
# =============================================================================
@pytest.mark.parametrize("dependency", ["get_writer_db_session", "get_read_only_db_session"])
async def test_session_dependency_rolls_back_exactly_once_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    dependency: str,
):
    """핸들러가 터져도 세션은 정리된다 — ROLLBACK 은 중복도 누락도 아닌 1회다.

    `AsyncSession.__aexit__` 의 `close()` 가 활성 트랜잭션을 이미 롤백하므로,
    Dependency 안의 명시적 `except` → `rollback()` 은 있으나 없으나 결과가 같다.
    그 블록을 지워도 이 계약이 깨지지 않는지 여기서 본다.
    """
    from sqlalchemy import event, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.db.router import read_intent

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    rollbacks: list[object] = []
    event.listen(engine.sync_engine, "rollback", rollbacks.append)
    monkeypatch.setattr(
        db_session,
        "AsyncSessionLocal",
        async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False),
    )

    generator = getattr(db_session, dependency)()
    session = await anext(generator)
    try:
        # 실제로 연결을 잡아야 롤백할 트랜잭션이 생긴다.
        # read-only 세션에서도 도는 구문이어야 하므로 읽기 의도를 붙인다 — 태그 없는
        # ``text()`` 는 읽기 전용 세션에서 기본 거부된다(fail-closed).
        await session.execute(read_intent(text("SELECT 1")))
        with pytest.raises(RuntimeError):
            await generator.athrow(RuntimeError("핸들러 실패(모의)"))
    finally:
        await engine.dispose()

    assert len(rollbacks) == 1, f"ROLLBACK 이 {len(rollbacks)}회 — 중복 또는 누락"
    assert not session.in_transaction(), "예외 경로에서 세션이 닫히지 않았다"
