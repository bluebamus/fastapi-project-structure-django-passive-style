"""
User Service

사용자 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계(commit/rollback)는 호출하는 의존성(또는 background_session)이 책임진다.

인가(service-hardening F2): 목록·생성·삭제는 라우트가 슈퍼유저로 막고, 단건 조회·수정은
여기서 ``OwnershipPolicy`` 로 "본인 또는 슈퍼유저" 를 판정한다 — **존재 확인보다 먼저**
판정해 남의 ID 를 넣어 404/403 차이로 존재 여부를 알아내지 못하게 한다. 권한 필드
(``is_active``·``is_superuser``) 변경은 슈퍼유저만 한다. 비활성화·강등·삭제는 그 사용자의
refresh family 와 관리 화면 세션을 모두 폐기한다(``UserSessionRevoker`` — 관리 화면의 ``UserAdmin`` 훅과
같은 폐기 집합, admin-session-hardening ADR-005). 폐기는 커밋 전이다 — 실패하면 커밋되지 않는다.
"""

import asyncio
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import ForbiddenException
from app.core.security import OwnershipPolicy, PasswordHasher, Principal
from app.core.security.revocation import UserSessionRevoker
from app.core.services.services_base import BaseService
from app.features.user.exceptions import (
    UsernameDuplicateException,
    UserNotFoundException,
)
from app.features.user.models.models import User
from app.features.user.repositories.user_repository import UserRepository
from app.features.user.schemas.user_schema import UserCreate, UserUpdate


class UserService(BaseService):
    """사용자 비즈니스 로직 (세션 기반).

    Args:
        session: DB 세션.
        ownership: 본인·슈퍼유저 판정.
        password_hasher: 생성 시 비밀번호 해시 — 쓰기용 provider 만 넘긴다.
        revoker: 비활성화·강등·삭제 시 refresh·관리 세션 폐기 — 쓰기용 provider 만 넘긴다
            (읽기 경로가 Redis 에 묶이지 않게 한다).
    """

    def __init__(
        self,
        session: AsyncSession,
        ownership: OwnershipPolicy,
        password_hasher: PasswordHasher | None = None,
        revoker: UserSessionRevoker | None = None,
    ) -> None:
        super().__init__(session)
        self.repository = UserRepository(session)
        self.ownership = ownership
        self._password_hasher = password_hasher
        self._revoker = revoker

    async def create_user(self, data: UserCreate) -> User:
        """사용자를 생성한다. 사용자명 중복 시 UsernameDuplicateException."""
        self.log.debug("사용자 생성: username=%s", data.username)
        if await self.repository.get_by_username(data.username) is not None:
            raise UsernameDuplicateException(detail={"username": data.username})
        # 해시는 CPU 집약적이라 이벤트 루프를 막지 않도록 스레드로 격리한다.
        hashed = await asyncio.to_thread(self._writer_hasher().hash, data.password)
        values = data.model_dump(exclude={"password"})
        return await self.repository.create({**values, "hashed_password": hashed})

    async def get_user(self, user_id: str, principal: Principal) -> User:
        """사용자를 조회한다. 본인·슈퍼유저가 아니면 403(존재 여부와 무관), 없으면 404."""
        self.ownership.ensure_can_modify(user_id, principal)
        return await self._get_existing(user_id)

    async def list_users(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[User], int]:
        """사용자 목록과 전체 개수를 조회한다."""
        self.log.debug("사용자 목록 조회: skip=%s limit=%s", skip, limit)
        users = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return users, total

    async def update_user(self, user_id: str, data: UserUpdate, principal: Principal) -> User:
        """사용자를 부분 수정한다.

        본인·슈퍼유저가 아니면 403(존재 확인 전), 권한 필드를 일반 사용자가 바꾸면 403,
        없으면 404. 비활성화·강등이면 그 사용자의 refresh family 와 관리 세션을 모두 폐기한다.
        """
        self.log.debug("사용자 수정: id=%s", user_id)
        self.ownership.ensure_can_modify(user_id, principal)
        changes = data.model_dump(exclude_unset=True)
        if not principal.is_superuser and changes.keys() & UserUpdate.privileged_fields:
            raise ForbiddenException()
        existing = await self._get_existing(user_id)  # 존재 보장(없으면 404)
        updated = await self.repository.update(user_id, changes)
        if changes.get("is_active") is False or changes.get("is_superuser") is False:
            await self._writer_revoker().revoke(user_id)
        # updated 가 None 이면 변경행 0(동일 값 no-op, MySQL changed-rows 의미). 존재는 이미
        # 보장됐으므로 404 가 아니라 현재 엔티티를 반환한다.
        return updated if updated is not None else existing

    async def delete_user(self, user_id: str) -> None:
        """사용자를 삭제하고 refresh family·관리 세션을 모두 폐기한다. 없으면 UserNotFoundException."""
        self.log.debug("사용자 삭제: id=%s", user_id)
        deleted = await self.repository.delete(user_id)
        if not deleted:
            raise UserNotFoundException(detail={"id": user_id})
        await self._writer_revoker().revoke(user_id)

    async def _get_existing(self, user_id: str) -> User:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            raise UserNotFoundException(detail={"id": user_id})
        return user

    def _writer_hasher(self) -> PasswordHasher:
        if self._password_hasher is None:
            raise RuntimeError("쓰기용 provider(get_user_service)로 만든 서비스가 아니다")
        return self._password_hasher

    def _writer_revoker(self) -> UserSessionRevoker:
        if self._revoker is None:
            raise RuntimeError("쓰기용 provider(get_user_service)로 만든 서비스가 아니다")
        return self._revoker
