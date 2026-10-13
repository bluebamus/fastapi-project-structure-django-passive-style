"""Auth v1 API — 회원가입 / 로그인 / 토큰 재발급 / 로그아웃 / 현재 사용자.

뷰는 HTTP 역할만: 입력 수신 → 주입된 AuthService 호출 → 응답 변환. 레이트 리밋은
라우트 의존성(``register_rate_limit``·``login_rate_limit``)이 핸들러보다 먼저 건다.
DB 쓰기(register·login 의 재해시)는 응답 DTO 를 검증한 뒤 커밋한다.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.exception import ErrorResponse
from app.core.security import RateLimiter
from app.core.security.access import PublicWrite
from app.features.auth.dependencies.auth_dependencies import (
    get_auth_service,
    get_current_user,
    get_rate_limiter,
    login_rate_limit,
    register_rate_limit,
)
from app.features.auth.schemas.auth_schema import (
    AuthenticatedUserResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.features.auth.services.auth_service import AuthService
from app.features.user.models.models import User

router = APIRouter()

_UNAUTH: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse, "description": "인증 실패"}
}
_CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorResponse, "description": "사용자명 중복"}
}
_RATE_LIMITED: dict[int | str, dict[str, Any]] = {
    429: {
        "model": ErrorResponse,
        "description": "시도 한도 초과 — `Retry-After` 헤더의 초만큼 기다린다",
    }
}


@router.post(
    "/register",
    response_model=AuthenticatedUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    description="사용자명·이메일·비밀번호로 사용자를 생성합니다. ip 기준 레이트 리밋이 걸려 있습니다.",
    operation_id="authRegister",
    responses={**_CONFLICT, **_RATE_LIMITED},
    dependencies=[PublicWrite, Depends(register_rate_limit)],
)
async def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> AuthenticatedUserResponse:
    user = await service.register(payload)
    response = AuthenticatedUserResponse.model_validate(user)  # 검증 실패면 커밋하지 않는다
    await service.commit()
    return response


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="로그인(OAuth2 password)",
    description=(
        "username/password(form)로 access·refresh 토큰을 발급합니다. ip 기준과 ip+username "
        "기준 레이트 리밋이 걸려 있고, 성공하면 ip+username 카운터를 초기화합니다."
    ),
    dependencies=[PublicWrite],
    operation_id="authLogin",
    responses={**_UNAUTH, **_RATE_LIMITED},
)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    attempt_key: str = Depends(login_rate_limit),
    limiter: RateLimiter = Depends(get_rate_limiter),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = await service.authenticate(form.username, form.password)
    tokens = await service.issue_tokens(user)
    await service.commit()  # bcrypt → Argon2 재해시가 있으면 여기서 저장된다
    await limiter.reset(attempt_key)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="토큰 재발급(회전)",
    description=(
        "Refresh Token 으로 새 access·refresh 토큰을 발급합니다. 쓴 refresh 토큰은 소비되며, "
        "같은 토큰을 다시 쓰면 재사용으로 보고 그 family 전체를 폐기합니다."
    ),
    dependencies=[PublicWrite],
    operation_id="authRefresh",
    responses=_UNAUTH,
)
async def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    return await service.rotate(payload.refresh_token)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="로그아웃",
    description=(
        "Refresh Token 의 family 를 폐기합니다(멱등). access 토큰은 만료까지 유효하므로 "
        "클라이언트가 버립니다."
    ),
    dependencies=[PublicWrite],
    operation_id="authLogout",
    responses=_UNAUTH,
)
async def logout(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(payload.refresh_token)


@router.get(
    "/me",
    response_model=AuthenticatedUserResponse,
    summary="현재 사용자",
    description="Bearer access token 으로 현재 로그인 사용자를 반환합니다(보호 엔드포인트).",
    operation_id="authMe",
    responses=_UNAUTH,
)
async def me(current_user: User = Depends(get_current_user)) -> AuthenticatedUserResponse:
    return AuthenticatedUserResponse.model_validate(current_user)
