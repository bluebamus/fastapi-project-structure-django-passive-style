"""JWT 발급·검증 (service-hardening ADR-014).

claims 는 ``sub, type, iat, nbf, exp, jti, iss, aud`` 가 기본이고 access 는 ``username``·
``su``(슈퍼유저 여부, bool — 단계 F2, ADR-030), refresh 는 ``fam``(회전 family id)을 더한다.
검증은 설정 알고리즘 하나만 받고(``alg`` 혼동 차단), 발급자·대상·필수 claim·토큰 종류를 모두 본다. 실패는 원인과 무관하게
``InvalidTokenException``(401) 하나다 — 원인을 나눠 알려 주면 위조 시도의 오라클이 된다.

access 와 refresh 는 서명 키가 다르다. 종류(``type``) 검사는 키가 같게 설정된 배포에서도
종류 혼동을 막는 두 번째 벽이다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, NamedTuple
from uuid import uuid4

import jwt

from app.core.exception import InvalidTokenException
from config import JWTSettings

TokenType = Literal["access", "refresh"]
ACCESS: TokenType = "access"
REFRESH: TokenType = "refresh"

#: 모든 토큰에 반드시 있어야 하는 claim — 하나라도 없으면 거부한다.
_REQUIRED_CLAIMS = ("exp", "iat", "nbf", "sub", "jti", "iss", "aud", "type")
_EXTRA_REQUIRED: dict[TokenType, tuple[str, ...]] = {
    ACCESS: ("username", "su"),
    REFRESH: ("fam",),
}
#: 종류별 추가 claim 의 값 타입 — 이름만 있고 타입이 다른 값(``"su": "true"``)도 거부한다.
_EXTRA_TYPES: dict[str, type] = {"username": str, "su": bool, "fam": str}


class IssuedToken(NamedTuple):
    """발급 결과 — 토큰 문자열, 그 ``jti``, 수명(초)."""

    token: str
    jti: str
    expires_in: int


class TokenService:
    """access/refresh 토큰을 발급하고 검증한다(프로세스당 하나 — provider 가 만든다).

    Args:
        settings: 키·알고리즘·발급자·대상·수명·허용 오차를 담은 ``JWTSettings``.
    """

    def __init__(self, settings: JWTSettings) -> None:
        self._settings = settings
        self._secrets: dict[TokenType, str] = {
            ACCESS: settings.ACCESS_TOKEN_SECRET_KEY,
            REFRESH: settings.REFRESH_TOKEN_SECRET_KEY,
        }
        self._lifetimes: dict[TokenType, timedelta] = {
            ACCESS: timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
            REFRESH: timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        }

    def issue_access(self, sub: str, username: str, is_superuser: bool) -> IssuedToken:
        """access 토큰을 발급한다. ``su`` 는 인가 의존성이 DB 조회 없이 읽는다(ADR-017)."""
        return self._issue(ACCESS, sub, {"username": username, "su": is_superuser})

    def issue_refresh(self, sub: str, family: str) -> IssuedToken:
        """refresh 토큰을 발급한다. ``family`` 는 회전으로 이어지는 토큰들이 공유한다."""
        return self._issue(REFRESH, sub, {"fam": family})

    def decode(self, token: str, expected_type: TokenType) -> dict[str, Any]:
        """토큰을 검증하고 claims 를 돌려준다.

        Raises:
            InvalidTokenException: 서명·만료·nbf·iss·aud·필수 claim·종류 중 하나라도 어긋남.
        """
        settings = self._settings
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                self._secrets[expected_type],
                algorithms=[settings.JWT_ALGORITHM],
                audience=settings.JWT_AUDIENCE,
                issuer=settings.JWT_ISSUER,
                leeway=settings.JWT_LEEWAY_SECONDS,
                options={"require": [*_REQUIRED_CLAIMS, *_EXTRA_REQUIRED[expected_type]]},
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidTokenException() from exc
        if claims["type"] != expected_type:
            raise InvalidTokenException()
        if not all(
            isinstance(claims[name], _EXTRA_TYPES[name]) for name in _EXTRA_REQUIRED[expected_type]
        ):
            raise InvalidTokenException()
        return claims

    def _issue(self, token_type: TokenType, sub: str, extra: dict[str, Any]) -> IssuedToken:
        now = datetime.now(UTC)
        lifetime = self._lifetimes[token_type]
        jti = uuid4().hex
        payload: dict[str, Any] = {
            "sub": sub,
            "type": token_type,
            "iat": now,
            "nbf": now,
            "exp": now + lifetime,
            "jti": jti,
            "iss": self._settings.JWT_ISSUER,
            "aud": self._settings.JWT_AUDIENCE,
            **extra,
        }
        token = jwt.encode(
            payload, self._secrets[token_type], algorithm=self._settings.JWT_ALGORITHM
        )
        return IssuedToken(token, jti, int(lifetime.total_seconds()))
