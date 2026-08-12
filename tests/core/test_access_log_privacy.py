"""접속 로그의 신뢰 경계와 개인정보 처리 (계획서 P1-2).

세 가지가 겹쳐 있었다:

1. **IP 위조** — `X-Forwarded-For` / `X-Real-IP` 를 검증 없이 그대로 썼다. 이
   헤더는 클라이언트가 마음대로 보낸다. 앞단에 신뢰할 프록시가 있을 때만 믿을 수
   있는 값인데, 직접 붙은 요청이 보낸 것도 그대로 받았다 — 감사 로그의 IP 를
   누구나 조작할 수 있었다.
2. **쿼리 원문 저장** — URL 에 토큰·이메일·검색어가 실려 오면 평문으로 쌓인다.
3. **세션 ID 원문 저장** — 이 테이블이 유출되면 곧바로 세션 탈취로 이어진다.

접속 로그 API 에 인증이 붙었더라도(F-02) 저장 자체를 줄이는 것이 마지막 방어선이다.
"""

import ipaddress

import pytest

from app.core.middlewares.user_info_middleware import UserInfoMiddleware
from config import middleware_settings

PEER = "203.0.113.9"  # 실제 TCP 피어 (신뢰 가능)
CLAIMED = "198.51.100.7"  # 클라이언트가 헤더로 주장하는 값


class _FakeClient:
    def __init__(self, host: str) -> None:
        self.host = host


class _FakeRequest:
    """미들웨어가 읽는 속성만 갖춘 최소 스텁."""

    def __init__(self, headers: dict[str, str] | None = None, peer: str | None = PEER) -> None:
        self.headers = headers or {}
        self.client = _FakeClient(peer) if peer else None


@pytest.fixture
def middleware():
    return UserInfoMiddleware(app=None)  # type: ignore[arg-type]


@pytest.fixture
def no_trusted_proxy(monkeypatch):
    monkeypatch.setattr(middleware_settings, "ACCESS_LOG_TRUSTED_PROXIES", [])


@pytest.fixture
def peer_is_trusted(monkeypatch):
    monkeypatch.setattr(middleware_settings, "ACCESS_LOG_TRUSTED_PROXIES", [f"{PEER}/32"])


# ---------------------------------------------------------------------------
# 1. 신뢰 경계
# ---------------------------------------------------------------------------


def test_forwarded_header_is_ignored_from_untrusted_peer(middleware, no_trusted_proxy):
    """신뢰 목록에 없는 상대가 보낸 X-Forwarded-For 는 무시한다."""
    request = _FakeRequest({"X-Forwarded-For": CLAIMED})
    assert middleware._get_client_ip(request) == PEER


def test_real_ip_header_is_ignored_from_untrusted_peer(middleware, no_trusted_proxy):
    request = _FakeRequest({"X-Real-IP": CLAIMED})
    assert middleware._get_client_ip(request) == PEER


def test_forwarded_header_is_used_from_trusted_proxy(middleware, peer_is_trusted):
    """신뢰 프록시 뒤에서는 전달 헤더가 실제 클라이언트 주소다 — 막으면 안 된다."""
    request = _FakeRequest({"X-Forwarded-For": CLAIMED})
    assert middleware._get_client_ip(request) == CLAIMED


def test_forwarded_chain_takes_closest_untrusted_hop(middleware, peer_is_trusted):
    """체인 중 신뢰하지 않는 가장 오른쪽 항목이 클라이언트다.

    맨 앞을 그대로 쓰면 클라이언트가 체인 앞쪽에 가짜 항목을 끼워 넣어 위조할 수 있다.
    """
    request = _FakeRequest({"X-Forwarded-For": f"1.2.3.4, {CLAIMED}"})
    assert middleware._get_client_ip(request) == CLAIMED


def test_malformed_forwarded_value_falls_back_to_peer(middleware, peer_is_trusted):
    request = _FakeRequest({"X-Forwarded-For": "not-an-ip"})
    assert middleware._get_client_ip(request) == PEER


def test_client_ip_is_always_a_valid_address(middleware, no_trusted_proxy):
    request = _FakeRequest({"X-Forwarded-For": "'; DROP TABLE users;--"})
    ipaddress.ip_address(middleware._get_client_ip(request))  # 예외 없이 파싱된다


# ---------------------------------------------------------------------------
# 2. 민감 쿼리 마스킹
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["token", "access_token", "api_key", "password", "secret", "code"])
def test_sensitive_query_values_are_redacted(key):
    from app.core.middlewares.user_info_middleware import redact_query_string

    redacted = redact_query_string(f"{key}=super-secret-value&page=2")

    assert "super-secret-value" not in redacted
    assert "page=2" in redacted, "민감하지 않은 값은 그대로 남아야 디버깅에 쓸 수 있다"


def test_redaction_is_case_insensitive():
    from app.core.middlewares.user_info_middleware import redact_query_string

    assert "abc" not in redact_query_string("ACCESS_TOKEN=abc")


def test_redaction_keeps_none_as_none():
    from app.core.middlewares.user_info_middleware import redact_query_string

    assert redact_query_string(None) is None


# ---------------------------------------------------------------------------
# 3. 세션 ID
# ---------------------------------------------------------------------------


def test_session_id_is_never_stored_verbatim():
    from app.core.middlewares.user_info_middleware import hash_session_id

    raw = "abcdef0123456789"
    hashed = hash_session_id(raw)

    assert hashed is not None
    assert raw not in hashed


def test_session_id_hash_is_stable_for_correlation():
    """같은 세션은 같은 값이어야 로그를 묶어 볼 수 있다(원문 없이도)."""
    from app.core.middlewares.user_info_middleware import hash_session_id

    assert hash_session_id("session-a") == hash_session_id("session-a")
    assert hash_session_id("session-a") != hash_session_id("session-b")


def test_missing_session_id_stays_none():
    from app.core.middlewares.user_info_middleware import hash_session_id

    assert hash_session_id(None) is None


def test_collected_info_carries_no_raw_secrets(middleware, no_trusted_proxy, monkeypatch):
    """수집 결과 전체를 훑어 원문이 새지 않는지 확인한다."""

    class _Params:
        def __str__(self) -> str:
            return "token=leaked-token&q=hello"

        def __bool__(self) -> bool:
            return True

    class _Url:
        path = "/api/v1/user/users"

    request = _FakeRequest({"User-Agent": "pytest"})
    request.url = _Url()  # type: ignore[attr-defined]
    request.query_params = _Params()  # type: ignore[attr-defined]
    request.method = "GET"  # type: ignore[attr-defined]
    request.cookies = {"session_id": "raw-session-value"}  # type: ignore[attr-defined]

    class _State:
        user_id = None

    request.state = _State()  # type: ignore[attr-defined]

    info = middleware._collect_request_info(request)
    blob = repr(info)

    assert "leaked-token" not in blob
    assert "raw-session-value" not in blob
    assert "q=hello" in blob, "민감하지 않은 쿼리는 남는다"
