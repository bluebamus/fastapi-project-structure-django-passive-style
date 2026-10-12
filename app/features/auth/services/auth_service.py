"""Auth 서비스 — 회원가입 / 인증 / 토큰 발급·회전·폐기.

user 도메인의 `User` 모델·`UserRepository` 에 대해 인증한다(자격증명은 users.hashed_password).
auth 는 횡단 관심사라 user 식별 모델에 의존하는 것을 허용한다.

해시·토큰·refresh 기록은 core security 의 부품을 **생성자로 주입받는다**(service-hardening
ADR-022) — 조립은 ``dependencies/auth_dependencies.py`` 의 provider 가 한다.
"""

import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import InvalidTokenException
from app.core.security import REFRESH, PasswordHasher, RefreshTokenStore, TokenService
from app.core.services.services_base import BaseService
from app.features.auth.exceptions import (
    InvalidCredentialsException,
    UsernameAlreadyExistsException,
)
from app.features.auth.schemas.auth_schema import RegisterRequest, TokenResponse
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository


async def verify_credentials(
    users: UserRepository, password_hasher: PasswordHasher, username: str, password: str
) -> User:
    """사용자명/비밀번호 검증 — API 로그인과 ``/admin`` 로그인이 함께 쓰는 한 곳.

    사용자가 없거나 비밀번호가 없는 계정도 해시기가 더미 해시로 같은 비용의 검증을
    치른다(응답 시간으로 사용자명을 열거하는 타이밍 공격 방지). 저장 해시를 바꿔야
    하면(bcrypt → Argon2 이전) 새 해시를 flush 까지 해 둔다 — 커밋은 호출자가 한다.

    Raises:
        InvalidCredentialsException: 사용자 없음·비활성·비밀번호 불일치(사유를 구분하지 않는다).
    """
    user = await users.get_by_username(username)
    stored = user.hashed_password if user is not None else None
    password_ok, new_hash = await asyncio.to_thread(
        password_hasher.verify_and_update, password, stored
    )
    if user is None or not user.is_active or not password_ok:
        raise InvalidCredentialsException()
    if new_hash is not None:
        await users.update(user.id, {"hashed_password": new_hash})
    return user


class AuthService(BaseService):
    """인증 비즈니스 로직. 커밋은 쓰기 핸들러가 한다."""

    def __init__(
        self,
        session: AsyncSession,
        password_hasher: PasswordHasher,
        token_service: TokenService,
        refresh_store: RefreshTokenStore,
    ) -> None:
        super().__init__(session)
        self.users = UserRepository(session)
        self.password_hasher = password_hasher
        self.token_service = token_service
        self.refresh_store = refresh_store

    async def register(self, data: RegisterRequest) -> User:
        """사용자를 생성한다(사용자명 중복 시 409)."""
        if await self.users.get_by_username(data.username) is not None:
            raise UsernameAlreadyExistsException()
        # 해시는 CPU 집약적이라 이벤트 루프를 막지 않도록 스레드로 격리한다.
        hashed = await asyncio.to_thread(self.password_hasher.hash, data.password)
        return await self.users.create(
            {
                "username": data.username,
                "email": data.email,
                "hashed_password": hashed,
            }
        )

    async def authenticate(self, username: str, password: str) -> User:
        """사용자명/비밀번호를 검증하고 사용자를 반환한다(실패 시 401, ``verify_credentials``)."""
        return await verify_credentials(self.users, self.password_hasher, username, password)

    async def issue_tokens(self, user: User) -> TokenResponse:
        """새 family 로 access·refresh 토큰을 발급한다(로그인)."""
        return await self._issue(user, family=uuid4().hex)

    async def rotate(self, refresh_token: str) -> TokenResponse:
        """refresh 토큰을 소비하고 같은 family 로 새 토큰 쌍을 발급한다.

        - 이미 소비된 토큰(재사용) → 탈취 신호로 보고 family 를 폐기한 뒤 401.
        - family 가 폐기됐음 → 401.
        - 사용자가 없거나 비활성 → family 를 폐기한 뒤 401.
        """
        claims = self.token_service.decode(refresh_token, REFRESH)
        family: str = claims["fam"]
        if not await self.refresh_store.consume(claims["jti"]):
            await self.refresh_store.revoke_family(family)
            self.log.warning("refresh 토큰 재사용 감지 — family 폐기 sub=%s", claims["sub"])
            raise InvalidTokenException()
        if await self.refresh_store.is_family_revoked(family):
            raise InvalidTokenException()
        user = await self.users.get_by_id(claims["sub"])
        if user is None or not user.is_active:
            await self.refresh_store.revoke_family(family)
            raise InvalidTokenException()
        return await self._issue(user, family=family)

    async def logout(self, refresh_token: str) -> None:
        """refresh 토큰의 family 를 폐기한다(멱등 — 이미 폐기됐어도 성공)."""
        claims = self.token_service.decode(refresh_token, REFRESH)
        await self.refresh_store.revoke_family(claims["fam"])
        await self.refresh_store.consume(claims["jti"])

    async def _issue(self, user: User, *, family: str) -> TokenResponse:
        access = self.token_service.issue_access(user.id, user.username, user.is_superuser)
        refresh = self.token_service.issue_refresh(user.id, family)
        await self.refresh_store.register(refresh.jti, user.id, family)
        return TokenResponse(
            access_token=access.token,
            refresh_token=refresh.token,
            expires_in=access.expires_in,
        )
