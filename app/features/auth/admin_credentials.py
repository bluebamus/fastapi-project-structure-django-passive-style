"""/admin 로그인의 자격 확인 — 사용자 저장소를 아는 쪽 구현 (admin-login ADR-002).

core 의 ``AdminAuthBackend`` 는 사용자 모델을 모른다. 이 클래스가 ``AdminCredentials`` 계약을
구현하고, ``AuthConfig.ready()`` 가 그 팩토리를 core 훅에 등록한다. 비밀번호 확인과
bcrypt → Argon2 재해시는 API 로그인과 같은 ``verify_credentials`` 를 쓴다.

세션은 요청 스코프 DI 밖이라 세션 팩토리(기본 ``background_session``)로 연다 — SQLAdmin
라우트는 FastAPI 의존성을 거치지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import PasswordHasher
from app.features.auth.exceptions import InvalidCredentialsException
from app.features.auth.services.auth_service import verify_credentials
from app.features.user.repositories.user_repository import UserRepository

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class UserAdminCredentials:
    """활성 슈퍼유저만 관리자로 인정한다.

    Args:
        session_factory: 요청 밖 세션 컨텍스트(``background_session``).
        password_hasher: core ``PasswordHasher`` (provider 가 만든 프로세스 공용 인스턴스).
    """

    def __init__(self, session_factory: SessionFactory, password_hasher: PasswordHasher) -> None:
        self.session_factory = session_factory
        self.password_hasher = password_hasher

    async def verify(self, username: str, password: str) -> str | None:
        async with self.session_factory() as session:
            try:
                user = await verify_credentials(
                    UserRepository(session), self.password_hasher, username, password
                )
            except InvalidCredentialsException:
                return None
            # 비밀번호가 맞으면 재해시(있다면)는 저장한다 — 슈퍼유저 여부와 무관한 사용자 자신의 값이다.
            await session.commit()
            return user.id if user.is_superuser else None

    async def is_admin(self, user_id: str) -> bool:
        async with self.session_factory() as session:
            user = await UserRepository(session).get_by_id(user_id)
            return user is not None and user.is_active and user.is_superuser


def default_admin_credentials() -> UserAdminCredentials:
    """운영 조립 — ``background_session`` + core provider 의 ``PasswordHasher``."""
    from app.core.db.session import background_session
    from app.core.security.dependencies import get_password_hasher

    return UserAdminCredentials(background_session, get_password_hasher())
