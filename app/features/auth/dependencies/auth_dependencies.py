"""Auth 의존성 — 보안 부품 조립(provider) · 레이트 리밋 · OAuth2 현재 사용자 해석.

협력 객체는 여기서 조립해 생성자로 넘긴다(service-hardening ADR-022). 상태 없는 부품
(해시기·토큰 서비스·IP 해석기)은 프로세스에 하나, Redis 를 쓰는 부품은 요청마다
``get_redis`` 가 준 클라이언트로 만든다. 테스트는 ``app.dependency_overrides[get_redis]``
에 fakeredis 를 넣거나 provider 자체를 바꾼다.
"""

import hashlib
from functools import lru_cache

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.router import using_writer
from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.core.exception import InvalidTokenException, TooManyRequestsException
from app.core.middlewares.client_ip import ClientIPResolver
from app.core.redis import get_redis
from app.core.security import (
    PasswordHasher,
    Principal,
    RateLimiter,
    RefreshTokenStore,
    TokenService,
)
from app.core.security.dependencies import (
    get_current_principal,
    get_password_hasher,
    get_refresh_token_store,
    get_token_service,
)
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from config import jwt_settings, middleware_settings


# =============================================================================
# 부품 provider — 해시기·토큰 서비스·refresh 기록은 core 의 provider 를 그대로 쓴다
# (``app.core.security.dependencies``). 다른 기능의 인가 의존성과 같은 객체라, 테스트가
# override 하면 모든 기능에 한 번에 적용된다.
# =============================================================================
@lru_cache
def get_client_ip_resolver() -> ClientIPResolver:
    """접속 로그 미들웨어와 같은 신뢰 홉 수로 클라이언트 IP 를 정한다."""
    return ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS)


def get_rate_limiter(redis: Redis = Depends(get_redis)) -> RateLimiter:
    """고정 창 레이트 리밋."""
    return RateLimiter(redis)


async def get_auth_service(
    session: AsyncSession = Depends(get_writer_db_session),
    password_hasher: PasswordHasher = Depends(get_password_hasher),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
) -> AuthService:
    """AuthService 를 구성해 제공한다(쓰기용 — 커밋은 핸들러가 한다).

    이전에는 `yield` 이후 커밋했으나, FastAPI 상위 버전에서 yield dependency 의
    종료 코드가 **응답 전송 후에** 실행되도록 바뀌어 커밋 실패가 201 로 둔갑했다.
    커밋을 핸들러 본문으로 옮겨 응답 생성 전에 끝나도록 보장한다(P1-3).
    """
    return AuthService(session, password_hasher, token_service, refresh_store)


# =============================================================================
# 레이트 리밋 — 라우트 의존성으로 건다(핸들러 본문이 아니다, ADR-016)
# =============================================================================
async def _enforce(limiter: RateLimiter, key: str, limit: int, window: int) -> None:
    result = await limiter.hit(key, limit, window)
    if not result.allowed:
        raise TooManyRequestsException(result.retry_after)


def _login_user_key(ip: str, username: str) -> str:
    """ip+username 카운터 키. 사용자명은 소문자로 접고 해시해 키 길이를 고정한다."""
    digest = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
    return f"login:user:{ip}:{digest}"


async def login_rate_limit(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    limiter: RateLimiter = Depends(get_rate_limiter),
    ip_resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> str:
    """로그인 시도를 ip 기준·ip+username 기준으로 센다. 넘으면 429.

    Returns:
        ip+username 카운터 키 — 로그인 성공 시 핸들러가 이 키를 초기화한다.
    """
    ip = ip_resolver.resolve(request)
    await _enforce(
        limiter,
        f"login:ip:{ip}",
        jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS,
        jwt_settings.AUTH_LOGIN_WINDOW_SECONDS,
    )
    user_key = _login_user_key(ip, form.username)
    await _enforce(
        limiter,
        user_key,
        jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS,
        jwt_settings.AUTH_LOGIN_WINDOW_SECONDS,
    )
    return user_key


async def register_rate_limit(
    request: Request,
    limiter: RateLimiter = Depends(get_rate_limiter),
    ip_resolver: ClientIPResolver = Depends(get_client_ip_resolver),
) -> None:
    """회원가입 시도를 ip 기준으로 센다. 넘으면 429."""
    await _enforce(
        limiter,
        f"register:ip:{ip_resolver.resolve(request)}",
        jwt_settings.AUTH_REGISTER_MAX_ATTEMPTS,
        jwt_settings.AUTH_REGISTER_WINDOW_SECONDS,
    )


# =============================================================================
# 현재 사용자
# =============================================================================
async def get_current_user(
    principal: Principal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_read_only_db_session),
) -> User:
    """Bearer access token 을 검증해 현재 사용자 **엔티티**를 반환한다(실패 시 401).

    토큰 검증은 core 의 ``get_current_principal`` 이 하고(``request.state.user_id`` 도 채운다),
    여기서는 읽기 전용 세션의 ``UserRepository`` 로 사용자를 다시 읽어 활성 여부를 본다 —
    ``/me`` 처럼 사용자 엔티티가 필요한 곳에서만 쓴다(인가만 필요하면 ``CurrentPrincipal``).
    커밋하는 ``get_auth_service`` 에 기대지 않으므로 인증+쓰기 의존성을 함께 쓰는
    엔드포인트에서 한 세션에 커밋 주체가 둘이 되는 이중 커밋 위험이 없고, 인증된 읽기
    요청마다 불필요한 COMMIT 왕복도 없다(검수 W2/REQ-009). 읽기 전용 표시는 그대로 두고 **primary 에
    고정**한다(integration-e2e ADR-012 결정 5) — replica 에서 읽으면 복제 지연 중 가입 직후의 유효한 토큰이 401 이
    되고, 비활성화·삭제가 복제될 때까지 반영되지 않는다(integration-e2e F-008). 나머지 읽기 라우팅은 그대로다.

    쓰기 의존성과 함께 쓰이는 라우트가 생기면 세션이 둘로 나뉜다(읽기용·쓰기용).
    인증 단계에서 읽은 객체를 쓰기 세션에서 수정하려 들면 다른 세션의 인스턴스라
    반영되지 않는다. 그런 라우트를 만들 때는 쓰기 세션에서 다시 조회할 것.
    """
    using_writer(session)
    user = await UserRepository(session).get_by_id(principal.id)
    if user is None or not user.is_active:
        raise InvalidTokenException()
    return user
