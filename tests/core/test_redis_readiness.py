"""Redis 필수 — ``get_redis`` provider 와 ``/ready`` 의 DB·Redis 확인 (service-hardening ADR-011·C-10).

lifespan 없이 ``create_app()`` 만 만들고 ``app.state.redis`` 에 가짜를 넣는다 — 실제 Redis·DB 에
닿지 않는다. DB ping 은 ``bootstrap.ping_writer_db`` 를 monkeypatch 한다.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core import bootstrap
from app.core.exception import ServiceUnavailableException
from app.core.redis import get_redis

SECRET = "SUPERSECRET-redis-pw"


class FakeRedis:
    """``PING`` 결과를 정할 수 있는 가짜 클라이언트."""

    def __init__(self, *, error: Exception | None = None, delay: float = 0.0) -> None:
        self.error = error
        self.delay = delay
        self.pings = 0

    async def ping(self) -> bool:
        self.pings += 1
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return True


def _request_with_state(**state: object) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


# =============================================================================
# get_redis provider
# =============================================================================
def test_get_redis_returns_the_lifespan_client():
    client = FakeRedis()

    assert get_redis(_request_with_state(redis=client)) is client  # type: ignore[arg-type]


@pytest.mark.parametrize("state", [{}, {"redis": None}], ids=["unset", "closed"])
def test_get_redis_without_a_client_is_503(state: dict[str, object]):
    """lifespan 밖(기동 전·종료 후)이면 503 — ``AttributeError`` 500 이 아니다."""
    with pytest.raises(ServiceUnavailableException) as exc:
        get_redis(_request_with_state(**state))  # type: ignore[arg-type]

    assert exc.value.status_code == 503


# =============================================================================
# /ready
# =============================================================================
def _ready_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    redis: FakeRedis | None,
    db_error: Exception | None = None,
) -> TestClient:
    async def ping_db(timeout: float = 0.0) -> None:
        if db_error is not None:
            raise db_error

    monkeypatch.setattr(bootstrap, "ping_writer_db", ping_db)
    app = bootstrap.create_app()
    app.state.redis = redis
    return TestClient(app, raise_server_exceptions=False)


def test_ready_is_200_when_db_and_redis_answer(monkeypatch: pytest.MonkeyPatch):
    redis = FakeRedis()
    response = _ready_client(monkeypatch, redis=redis).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert redis.pings == 1, "/ready 가 Redis 를 확인하지 않았다"


def test_ready_is_503_when_redis_fails_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    error = ConnectionError(f"redis://:{SECRET}@cache:6379/0 연결 거부")
    with caplog.at_level(logging.WARNING):
        response = _ready_client(monkeypatch, redis=FakeRedis(error=error)).get("/ready")

    assert response.status_code == 503
    assert SECRET not in response.text
    assert "6379" not in response.text
    readiness_logs = [r.getMessage() for r in caplog.records if "[Readiness]" in r.getMessage()]
    assert readiness_logs == ["[Readiness] Redis 준비 확인 실패: ConnectionError"]
    assert SECRET not in caplog.text


def test_ready_is_503_when_redis_times_out(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """응답 없는 Redis 는 readiness 예산(설정 2초) 안에 잘린다 — 여기서는 예산을 줄여 본다."""
    monkeypatch.setattr(bootstrap, "READINESS_TIMEOUT_SECONDS", 0.05)
    with caplog.at_level(logging.WARNING):
        response = _ready_client(monkeypatch, redis=FakeRedis(delay=5.0)).get("/ready")

    assert response.status_code == 503
    assert "[Readiness] Redis 준비 확인 실패: TimeoutError" in caplog.text


def test_ready_is_503_when_db_fails_even_if_redis_answers(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    error = RuntimeError(f"mysql+aiomysql://root:{SECRET}@db:3306/app 접속 실패")
    with caplog.at_level(logging.WARNING):
        response = _ready_client(monkeypatch, redis=FakeRedis(), db_error=error).get("/ready")

    assert response.status_code == 503
    assert SECRET not in response.text
    assert "[Readiness] DB 준비 확인 실패: RuntimeError" in caplog.text
    assert "Redis 준비 확인 실패" not in caplog.text
    assert SECRET not in caplog.text


def test_ready_reports_both_failures(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """둘 다 확인한다 — 첫 실패에서 멈추면 운영자가 두 번째 원인을 못 본다."""
    with caplog.at_level(logging.WARNING):
        response = _ready_client(
            monkeypatch,
            redis=FakeRedis(error=ConnectionError("x")),
            db_error=RuntimeError("y"),
        ).get("/ready")

    assert response.status_code == 503
    assert "DB 준비 확인 실패" in caplog.text
    assert "Redis 준비 확인 실패" in caplog.text


def test_ready_is_503_without_a_redis_client(monkeypatch: pytest.MonkeyPatch):
    response = _ready_client(monkeypatch, redis=None).get("/ready")

    assert response.status_code == 503
