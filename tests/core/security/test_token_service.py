"""TokenService — claims·검증 거부 사례 (service-hardening ADR-014).

거부 사례는 서명 키로 직접 만든 토큰으로 시험한다 — 서명이 맞아도 claim 하나가
어긋나면 거부돼야 한다는 것이 요점이다.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest

from app.core.exception import InvalidTokenException
from app.core.security import ACCESS, REFRESH, TokenService
from config import JWTSettings

ACCESS_KEY = "test-access-secret-" + "0123456789abcdef" * 4
REFRESH_KEY = "test-refresh-secret-" + "0123456789abcdef" * 4


def _settings(**overrides: Any) -> JWTSettings:
    values: dict[str, Any] = {
        "ACCESS_TOKEN_SECRET_KEY": ACCESS_KEY,
        "REFRESH_TOKEN_SECRET_KEY": REFRESH_KEY,
        "JWT_ISSUER": "test-issuer",
        "JWT_AUDIENCE": "test-audience",
        "JWT_LEEWAY_SECONDS": 0,
        **overrides,
    }
    return JWTSettings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture
def service() -> TokenService:
    return TokenService(_settings())


def _claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": "user-1",
        "type": "access",
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "jti": "a" * 32,
        "iss": "test-issuer",
        "aud": "test-audience",
        "username": "alice",
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _forge(claims: dict[str, Any], key: str = ACCESS_KEY, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


# ---------------------------------------------------------------------------
# 발급
# ---------------------------------------------------------------------------
def test_access_token_carries_all_claims(service):
    issued = service.issue_access("user-1", "alice")

    claims = service.decode(issued.token, ACCESS)

    assert claims["sub"] == "user-1"
    assert claims["type"] == "access"
    assert claims["username"] == "alice"
    assert claims["iss"] == "test-issuer"
    assert claims["aud"] == "test-audience"
    assert claims["jti"] == issued.jti and len(issued.jti) == 32
    assert claims["nbf"] == claims["iat"]
    assert claims["exp"] - claims["iat"] == 15 * 60 == issued.expires_in


def test_refresh_token_carries_family(service):
    issued = service.issue_refresh("user-1", "fam-1")

    claims = service.decode(issued.token, REFRESH)

    assert claims["fam"] == "fam-1"
    assert claims["type"] == "refresh"
    assert issued.expires_in == 7 * 86400


def test_every_token_gets_a_new_jti(service):
    assert service.issue_access("u", "n").jti != service.issue_access("u", "n").jti


# ---------------------------------------------------------------------------
# 거부
# ---------------------------------------------------------------------------
def test_expired_token_is_rejected(service):
    past = datetime.now(UTC) - timedelta(minutes=10)
    token = _forge(_claims(iat=past, nbf=past, exp=past + timedelta(minutes=1)))

    with pytest.raises(InvalidTokenException):
        service.decode(token, ACCESS)


def test_not_yet_valid_token_is_rejected(service):
    future = datetime.now(UTC) + timedelta(minutes=10)
    token = _forge(_claims(nbf=future, exp=future + timedelta(minutes=5)))

    with pytest.raises(InvalidTokenException):
        service.decode(token, ACCESS)


def test_leeway_tolerates_small_clock_skew():
    service = TokenService(_settings(JWT_LEEWAY_SECONDS=30))
    soon = datetime.now(UTC) + timedelta(seconds=10)

    assert service.decode(_forge(_claims(nbf=soon)), ACCESS)["sub"] == "user-1"


@pytest.mark.parametrize(("claim", "value"), [("aud", "other-audience"), ("iss", "other-issuer")])
def test_wrong_audience_or_issuer_is_rejected(service, claim, value):
    with pytest.raises(InvalidTokenException):
        service.decode(_forge(_claims(**{claim: value})), ACCESS)


@pytest.mark.parametrize(
    "missing", ["exp", "iat", "nbf", "sub", "jti", "iss", "aud", "type", "username"]
)
def test_missing_required_claim_is_rejected(service, missing):
    with pytest.raises(InvalidTokenException):
        service.decode(_forge(_claims(**{missing: None})), ACCESS)


def test_refresh_without_family_is_rejected(service):
    token = _forge(_claims(type="refresh", username=None), key=REFRESH_KEY)

    with pytest.raises(InvalidTokenException):
        service.decode(token, REFRESH)


def test_refresh_with_non_string_family_is_rejected(service):
    token = _forge(_claims(type="refresh", username=None, fam=123), key=REFRESH_KEY)

    with pytest.raises(InvalidTokenException):
        service.decode(token, REFRESH)


def test_type_confusion_is_rejected_even_with_the_right_key(service):
    """access 키로 서명했지만 type 이 refresh — 키가 같게 설정된 배포의 두 번째 벽."""
    token = _forge(_claims(type="refresh", fam="f"))

    with pytest.raises(InvalidTokenException):
        service.decode(token, ACCESS)


def test_refresh_token_is_not_accepted_as_access(service):
    token = service.issue_refresh("user-1", "fam").token

    with pytest.raises(InvalidTokenException):
        service.decode(token, ACCESS)


def test_other_algorithm_is_rejected(service):
    """설정 알고리즘(HS256) 하나만 받는다 — 같은 키의 HS512 도 거부한다."""
    with pytest.raises(InvalidTokenException):
        service.decode(_forge(_claims(), algorithm="HS512"), ACCESS)


def test_unsigned_token_is_rejected(service):
    token = jwt.encode(_claims(), None, algorithm="none")

    with pytest.raises(InvalidTokenException):
        service.decode(token, ACCESS)


def test_configured_algorithm_is_used_for_both_issue_and_verify():
    service = TokenService(_settings(JWT_ALGORITHM="HS512"))
    token = service.issue_access("user-1", "alice").token

    assert jwt.get_unverified_header(token)["alg"] == "HS512"
    assert service.decode(token, ACCESS)["sub"] == "user-1"


def test_tampered_token_is_rejected(service):
    token = service.issue_access("user-1", "alice").token

    with pytest.raises(InvalidTokenException):
        service.decode(token + "x", ACCESS)


def test_algorithm_setting_only_accepts_hmac():
    with pytest.raises(ValueError):
        _settings(JWT_ALGORITHM="none")
