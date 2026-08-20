"""Auth 도메인 스키마 — 회원가입/토큰 요청·응답."""

from pydantic import BaseModel, ConfigDict, Field

from app.utils.validators import EMAIL_PATTERN


class RegisterRequest(BaseModel):
    """회원가입 요청."""

    username: str = Field(..., min_length=1, max_length=100, description="사용자명(고유)")
    email: str = Field(..., max_length=255, pattern=EMAIL_PATTERN, description="이메일")
    password: str = Field(..., min_length=8, max_length=128, description="비밀번호(8자 이상)")


class AuthenticatedUserResponse(BaseModel):
    """인증이 돌려주는 사용자(민감 정보 제외).

    `user` 기능의 ``UserResponse`` 와 **다른 모델**이다 — 저쪽은 생성·수정 시각까지
    담는 정식 사용자 DTO 고, 이쪽은 로그인·`/me` 가 돌려주는 최소 정보다.

    이름을 굳이 다르게 두는 이유는 OpenAPI 때문이다. 서로 다른 모듈의 같은 클래스
    이름은 schema key 가 ``app__features__auth__schemas__auth_schema__UserResponse``
    처럼 **모듈 경로**로 노출된다. 그 이름은 파일을 옮기는 순간 바뀌고, 그때 이
    스키마로 생성한 클라이언트 코드가 통째로 깨진다(DOC-005).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str
    is_active: bool


class TokenResponse(BaseModel):
    """토큰 응답(OAuth2 bearer)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """토큰 재발급 요청."""

    refresh_token: str = Field(..., description="유효한 Refresh Token")
