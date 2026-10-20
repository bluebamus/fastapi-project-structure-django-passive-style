"""인증·인가 주입 경로 — core 하나만 의존하면 된다 (service-hardening ADR-017·C-11).

보안 부품 provider(``get_password_hasher``·``get_token_service``·``get_refresh_token_store``·
``get_admin_session_store``·``get_user_session_revoker``·``get_ownership_policy``)와 현재 주체 해석(``get_current_principal``)·슈퍼유저 강제
(``require_superuser``)를 둔다. 인증 기능도 같은 provider 를 쓴다 — 테스트가
``app.dependency_overrides`` 로 바꾸면 모든 기능에 한 번에 적용된다.

라우트의 접근 수준은 뷰마다 선언한다(``app.core.security.access`` — 선언이 없으면 기동 거부)::

    @router.get("/items", dependencies=[Public])                         # 공개 조회
    @router.get("/report", dependencies=[SuperuserRequired])             # 슈퍼유저
    async def create(payload: X, principal: CurrentPrincipal, ...)        # 인자 = 인증
    async def report(principal: SuperuserPrincipal, ...)                  # 인자 = 슈퍼유저

``get_current_principal`` 은 DB 를 조회하지 않는다. 비활성화·강등은 refresh 폐기로 다음
회전부터 막히고, 이미 발급된 access 는 만료(기본 15분)까지 유효하다(residual-risk R-002·R-014).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis

from app.core.exception import (
    ErrorResponse,
    ForbiddenException,
    InvalidTokenException,
    UnauthorizedException,
)
from app.core.redis import get_redis
from app.core.security.admin_session import AdminSessionStore, default_admin_session_store
from app.core.security.passwords import PasswordHasher
from app.core.security.principal import OwnershipPolicy, Principal
from app.core.security.refresh_store import RefreshTokenStore
from app.core.security.revocation import UserSessionRevoker
from app.core.security.tokens import ACCESS, TokenService
from config import jwt_settings

#: 토큰이 없을 때 FastAPI 기본 응답({"detail": ...}) 대신 저장소의 오류 봉투로 401 을 낸다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_BEARER_CHALLENGE = {"WWW-Authenticate": "Bearer"}

#: 보호 라우트의 OpenAPI 오류 응답 — ``responses={**UNAUTHORIZED_RESPONSE, ...}`` 로 싣는다.
UNAUTHORIZED_RESPONSE: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 필요 — 토큰 없음·만료·위조"}
}
FORBIDDEN_RESPONSE: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "권한 없음 — 소유자 또는 슈퍼유저만 가능"}
}
ADMIN_FORBIDDEN_RESPONSE: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorResponse, "description": "권한 없음 — 슈퍼유저 전용"}
}


# =============================================================================
# 부품 provider
# =============================================================================
@lru_cache
def get_password_hasher() -> PasswordHasher:
    """프로세스당 하나 — 생성 시 더미 해시를 한 번 만든다."""
    return PasswordHasher()


@lru_cache
def get_token_service() -> TokenService:
    """프로세스당 하나 — 설정에서 키·알고리즘·iss/aud 를 읽는다."""
    return TokenService(jwt_settings)


@lru_cache
def get_ownership_policy() -> OwnershipPolicy:
    """프로세스당 하나 — 상태가 없다."""
    return OwnershipPolicy()


def get_refresh_token_store(redis: Redis = Depends(get_redis)) -> RefreshTokenStore:
    """refresh 회전 기록. TTL 은 refresh 수명이다."""
    return RefreshTokenStore(redis, ttl_seconds=jwt_settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)


def get_admin_session_store(
    request: Request, redis: Redis = Depends(get_redis)
) -> AdminSessionStore | None:
    """관리 세션 저장소 — 사용자 비활성화·강등·삭제 시 그 사용자의 관리 세션을 지운다.

    관리 화면이 조립되지 않은 앱(``ADMIN_DISABLED=true``)에는 관리 세션이 없으므로 ``None`` 이다
    (admin-session-hardening ADR-001 — 이때 저장소를 만들지 않는다).
    """
    if getattr(request.app.state, "admin", None) is None:
        return None
    return default_admin_session_store(redis)


def get_user_session_revoker(
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
    admin_sessions: AdminSessionStore | None = Depends(get_admin_session_store),
) -> UserSessionRevoker:
    """사용자 단위 폐기(refresh + 관리 세션) — 관리 화면 훅과 같은 집합이다(admin-session-hardening ADR-005)."""
    return UserSessionRevoker(refresh_store, admin_sessions)


# =============================================================================
# 현재 주체
# =============================================================================
async def get_current_principal(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    token_service: TokenService = Depends(get_token_service),
) -> Principal:
    """Bearer access 토큰을 검증해 ``Principal`` 을 돌려준다(DB 조회 없음).

    성공하면 ``request.state.user_id`` 를 채워 접속 로그에 사용자 ID 가 남게 한다.

    Raises:
        UnauthorizedException: Authorization 헤더가 없음(401, ``WWW-Authenticate: Bearer``).
        InvalidTokenException: 서명·만료·claim·종류 중 하나라도 어긋남(401).
    """
    if not token:
        raise UnauthorizedException(headers=dict(_BEARER_CHALLENGE))
    try:
        claims = token_service.decode(token, ACCESS)
    except InvalidTokenException as exc:
        # 위조·만료도 같은 도전 헤더를 싣는다(RFC 6750 §3) — 없을 때만 붙으면 클라이언트가
        # "다시 인증하라" 는 신호를 놓친다(integration-e2e F-001).
        exc.headers = {**(exc.headers or {}), **_BEARER_CHALLENGE}
        raise
    principal = Principal(id=claims["sub"], username=claims["username"], is_superuser=claims["su"])
    request.state.user_id = principal.id
    return principal


async def require_superuser(
    principal: Principal = Depends(get_current_principal),
) -> Principal:
    """슈퍼유저만 통과시킨다(아니면 403)."""
    if not principal.is_superuser:
        raise ForbiddenException()
    return principal


#: 인증된 주체 — 핸들러 인자 타입으로 쓴다.
CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
#: 슈퍼유저 주체 — 핸들러 인자 타입으로 쓴다.
SuperuserPrincipal = Annotated[Principal, Depends(require_superuser)]
