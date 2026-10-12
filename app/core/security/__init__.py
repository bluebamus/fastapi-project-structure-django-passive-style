"""인증 보안 부품 (service-hardening ADR-013~ADR-016).

목적마다 클래스 하나다 — 비밀번호 해시(``PasswordHasher``), 토큰 발급·검증(``TokenService``),
refresh 회전 기록(``RefreshTokenStore``), 고정 창 레이트 리밋(``RateLimiter``), 요청 주체
(``Principal``)와 소유권 판정(``OwnershipPolicy``). 주입 경로(provider·``get_current_principal``·
``require_superuser``)는 ``app.core.security.dependencies`` 에 있다. 협력 객체
(Redis 클라이언트·설정)는 생성자로 받고, 조립은 기능의 provider 함수(``Depends``)가 한다.

core 에 두는 이유: 해시는 user 기능도(F2), 토큰 검증은 다른 기능의 인증 의존성도 써야 한다.
기능끼리는 import 하지 않으므로 공유 부품은 core 로 올린다.
"""

from app.core.security.passwords import PasswordHasher
from app.core.security.principal import OwnershipPolicy, Principal
from app.core.security.rate_limit import RateLimiter, RateLimitResult
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.tokens import ACCESS, REFRESH, IssuedToken, TokenService

__all__ = [
    "ACCESS",
    "REFRESH",
    "IssuedToken",
    "OwnershipPolicy",
    "PasswordHasher",
    "Principal",
    "RateLimitResult",
    "RateLimiter",
    "RefreshTokenStore",
    "TokenService",
]
