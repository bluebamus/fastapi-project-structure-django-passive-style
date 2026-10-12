"""접속 로그 수집 — 클라이언트 IP 해석과 미들웨어 기록 (service-hardening ADR-005·ADR-006).

* F-007: ``X-Forwarded-For`` 를 무조건 믿어 기록 IP 를 위조할 수 있었다 → ``ClientIPResolver``
* F-008: 처리되지 않은 예외로 끝난 요청(500)이 기록되지 않았다
* F-011: query string 원문(토큰 등)이 그대로 저장됐다
* 세션 쿠키 이름이 ``session_id`` 로 하드코딩돼 ``SESSION_COOKIE_NAME`` 과 어긋났다
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import parse_qsl

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from app.core.middlewares.access_log_sink import get_access_log_sink, set_access_log_sink
from app.core.middlewares.background_tasks import access_log_tasks
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.middlewares.user_info_middleware import UserInfoMiddleware
from config import session_settings


def _request(headers: dict[str, str] | None = None, peer: str | None = "10.0.0.9") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": (peer, 1234) if peer else None,
    }
    return Request(scope)


# =============================================================================
# ClientIPResolver
# =============================================================================
def test_zero_hops_ignores_proxy_headers():
    """기본값(0)에서는 누가 헤더를 보내도 소켓 주소를 쓴다."""
    resolver = ClientIPResolver(0)
    request = _request({"X-Forwarded-For": "6.6.6.6", "X-Real-IP": "7.7.7.7"})

    assert resolver.resolve(request) == "10.0.0.9"


def test_one_hop_takes_the_address_the_proxy_appended():
    """프록시 한 대: 클라이언트가 앞에 위조값을 넣어도 프록시가 붙인 오른쪽 끝을 쓴다."""
    resolver = ClientIPResolver(1)
    request = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7"})

    assert resolver.resolve(request) == "203.0.113.7"


def test_two_hops_take_the_second_from_the_right():
    resolver = ClientIPResolver(2)
    request = _request({"X-Forwarded-For": "6.6.6.6, 203.0.113.7, 10.0.0.2"})

    assert resolver.resolve(request) == "203.0.113.7"


def test_chain_shorter_than_the_hops_falls_back_to_the_peer():
    """선언한 프록시를 다 거치지 않은 요청이다 — 맨 왼쪽(클라이언트가 쓴 값)을 믿지 않는다."""
    resolver = ClientIPResolver(3)
    request = _request({"X-Forwarded-For": "6.6.6.6"})

    assert resolver.resolve(request) == "10.0.0.9"


def test_invalid_address_falls_back_to_the_peer():
    resolver = ClientIPResolver(1)

    assert resolver.resolve(_request({"X-Forwarded-For": "not-an-ip"})) == "10.0.0.9"
    assert resolver.resolve(_request({"X-Forwarded-For": "1.2.3.4, <script>"})) == "10.0.0.9"


def test_ipv6_address_is_accepted():
    resolver = ClientIPResolver(1)

    assert resolver.resolve(_request({"X-Forwarded-For": "2001:db8::1"})) == "2001:db8::1"


def test_real_ip_is_used_only_without_forwarded_for():
    resolver = ClientIPResolver(1)

    assert resolver.resolve(_request({"X-Real-IP": "203.0.113.8"})) == "203.0.113.8"
    assert (
        resolver.resolve(_request({"X-Real-IP": "6.6.6.6", "X-Forwarded-For": "203.0.113.7"}))
        == "203.0.113.7"
    )


def test_missing_peer_is_unknown():
    assert ClientIPResolver(0).resolve(_request(peer=None)) == "unknown"


def test_negative_hops_are_rejected():
    with pytest.raises(ValueError):
        ClientIPResolver(-1)


# =============================================================================
# UserInfoMiddleware — 실제 요청으로 무엇이 기록되는가
# =============================================================================
class _RecordingSink:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save(self, data: dict) -> None:
        self.saved.append(data)


@pytest.fixture
async def sink() -> AsyncIterator[_RecordingSink]:
    original = get_access_log_sink()
    recording = _RecordingSink()
    set_access_log_sink(recording)
    try:
        yield recording
    finally:
        set_access_log_sink(original)


def _app(hops: int = 0) -> FastAPI:
    app = FastAPI()
    app.add_middleware(UserInfoMiddleware, ip_resolver=ClientIPResolver(hops))

    @app.get("/ok")
    async def ok() -> dict:
        return {"ok": True}

    @app.get("/boom")
    async def boom() -> dict:
        raise RuntimeError("처리되지 않은 예외(모의)")

    return app


async def _get(app: FastAPI, url: str, **kwargs) -> None:
    transport = ASGITransport(app=app, raise_app_exceptions=False, client=("10.0.0.9", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get(url, **kwargs)
    await access_log_tasks.drain(timeout=2)


async def test_unhandled_exception_is_recorded_as_500(sink: _RecordingSink):
    await _get(_app(), "/boom")

    assert [entry["response_status"] for entry in sink.saved] == [500]
    assert sink.saved[0]["request_path"] == "/boom"


async def test_unhandled_exception_is_still_raised():
    """기록한 뒤 삼키지 않는다 — 바깥의 500 처리와 서버 로그가 그대로 동작해야 한다."""
    transport = ASGITransport(app=_app(), raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with pytest.raises(RuntimeError, match="모의"):
            await client.get("/boom")
    await access_log_tasks.drain(timeout=2)


async def test_sensitive_query_values_are_masked(sink: _RecordingSink):
    await _get(_app(), "/ok", params={"page": "2", "token": "s3cr3t", "Password": "pw", "q": "x y"})

    stored = sink.saved[0]["query_string"]
    assert "s3cr3t" not in stored and "pw" not in stored
    assert dict(parse_qsl(stored)) == {"page": "2", "token": "***", "Password": "***", "q": "x y"}


async def test_session_cookie_name_comes_from_settings(
    sink: _RecordingSink, monkeypatch: pytest.MonkeyPatch
):
    # 로컬 .env 값과 무관하게, 예전 하드코딩 이름(session_id)과 다른 이름으로 고정한다.
    monkeypatch.setattr(session_settings, "SESSION_COOKIE_NAME", "sid")

    await _get(_app(), "/ok", headers={"Cookie": "sid=sess-1; session_id=other"})

    assert sink.saved[0]["session_id"] == "sess-1"


async def test_injected_resolver_decides_the_recorded_ip(sink: _RecordingSink):
    headers = {"X-Forwarded-For": "6.6.6.6, 203.0.113.7"}

    await _get(_app(hops=0), "/ok", headers=headers)
    await _get(_app(hops=1), "/ok", headers=headers)

    assert [entry["ip_address"] for entry in sink.saved] == ["10.0.0.9", "203.0.113.7"]
