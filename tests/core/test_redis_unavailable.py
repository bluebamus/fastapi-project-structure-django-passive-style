"""Redis 연결 오류 → 503 (integration-e2e F-004 · 사용자 결정 1).

Redis 를 필수로 쓰는 API 경로(가입·로그인의 레이트 리밋, refresh·logout 의 회전 기록, 사용자 비활성화·삭제의 세션
폐기)가 Redis 에 닿지 못하면 처리되지 않은 예외 500 이 아니라 503 ``SERVICE_UNAVAILABLE`` 이다(fail-closed —
요청은 거부한다). ``Exception`` 핸들러로 가면 Starlette ``ServerErrorMiddleware`` 가 응답 뒤 예외를 다시 던져
traceback 이 두 번 남고 uvicorn 이 keep-alive 연결을 끊는다 — 여기서는 전송(ASGITransport)이 예외를 그대로
올리므로, 다시 던지면 테스트가 응답 대신 예외를 받는다.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.core.redis import get_redis
from app.core.security.dependencies import get_token_service
from app.features.user.models.models import User
from main import app
from tests.auth_headers import admin_headers
from tests.session_overrides import sqlite_session_overrides


class _DownRedis:
    """모든 명령이 연결 오류를 내는 Redis."""

    def __init__(self, error: type[Exception]) -> None:
        self.error = error

    def __getattr__(self, name: str) -> Any:
        def fail(*args: Any, **kwargs: Any) -> Any:
            raise self.error("Error 111 connecting to cache:6379. Connection refused.")

        return fail


@pytest_asyncio.fixture(
    params=[RedisConnectionError, RedisTimeoutError], ids=["connection", "timeout"]
)
async def down(request):
    async with sqlite_session_overrides(app) as maker:
        app.dependency_overrides[get_redis] = lambda: _DownRedis(request.param)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, maker


def _refresh_token() -> str:
    return get_token_service().issue_refresh(str(uuid4()), uuid4().hex).token


REQUESTS = {
    "register": (
        "POST",
        "/api/v1/auth/register",
        {"json": {"username": "u1", "email": "u1@example.com", "password": "Password-123"}},
    ),
    "login": (
        "POST",
        "/api/v1/auth/login",
        {"data": {"username": "u1", "password": "Password-123"}},
    ),
    "refresh": ("POST", "/api/v1/auth/refresh", {"json": None}),
    "logout": ("POST", "/api/v1/auth/logout", {"json": None}),
}


@pytest.mark.parametrize("name", sorted(REQUESTS))
async def test_redis_dependent_auth_paths_answer_503(down, name, caplog):
    client, _ = down
    method, path, kwargs = REQUESTS[name]
    if kwargs.get("json", "") is None:
        kwargs = {"json": {"refresh_token": _refresh_token()}}
    with caplog.at_level(logging.ERROR):
        response = await client.request(method, path, **kwargs)

    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error_code"] == "SERVICE_UNAVAILABLE"
    assert "6379" not in response.text and "Connection" not in response.text
    _assert_logged_once(caplog)


@pytest.mark.parametrize("change", ["deactivate", "delete"])
async def test_user_change_that_must_revoke_sessions_answers_503_and_does_not_commit(
    down, change, caplog
):
    client, maker = down
    async with maker() as session:
        user = User(username=f"v-{uuid4().hex[:6]}", email="v@example.com", hashed_password="x")
        session.add(user)
        await session.commit()
        user_id = user.id
    path = f"/api/v1/user/users/{user_id}"
    with caplog.at_level(logging.ERROR):
        if change == "delete":
            response = await client.delete(path, headers=admin_headers())
        else:
            response = await client.patch(path, json={"is_active": False}, headers=admin_headers())

    assert response.status_code == 503, response.text
    assert response.json()["error_code"] == "SERVICE_UNAVAILABLE"
    _assert_logged_once(caplog)
    async with maker() as session:
        kept = await session.get(User, user_id)
        assert kept is not None and kept.is_active, "세션 폐기가 실패했는데 변경이 커밋됐다"


def _assert_logged_once(caplog) -> None:
    """한 번만, traceback 과 함께 — 처리되지 않은 예외 기록(``[UnhandledException]``)은 없다."""
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert not [r for r in errors if "UnhandledException" in r.getMessage()], [
        r.getMessage() for r in errors
    ]
    with_traceback = [r for r in errors if r.exc_info]
    assert len(with_traceback) == 1, [r.getMessage() for r in errors]
