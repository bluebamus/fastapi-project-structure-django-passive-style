"""
SNS Service

피드 게시물 비즈니스 로직. 세션을 주입받아 Repository 를 구성한다.
트랜잭션 경계: 요청 경로는 쓰기 핸들러 본문이 응답 DTO 검증 뒤 `await service.commit()` 으로,
요청 밖은 background_session() 이 커밋한다. 서비스는 커밋하지 않는다(세션은 의존성이 연다).
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import OwnershipPolicy, Principal
from app.core.services.services_base import BaseService
from app.features.sns.exceptions import SnsPostNotFoundException
from app.features.sns.models.models import SnsPost
from app.features.sns.repositories.sns_post_repository import SnsPostRepository
from app.features.sns.schemas.sns_schema import SnsPostCreate, SnsPostUpdate


class SnsService(BaseService):
    """피드 게시물 비즈니스 로직 (세션 기반)."""

    def __init__(self, session: AsyncSession, ownership: OwnershipPolicy) -> None:
        super().__init__(session)
        self.ownership = ownership
        self.repository = SnsPostRepository(session)

    async def create_post(self, data: SnsPostCreate, principal: Principal) -> SnsPost:
        """게시물을 생성한다(커밋은 호출자가 수행).

        작성자(``author_id``·``author``)는 요청 본문이 아니라 인증 주체로 채운다(ADR-018).
        """
        self.log.debug("피드 게시물 생성: author=%s", principal.username)
        return await self.repository.create(
            {**data.model_dump(), "author_id": principal.id, "author": principal.username}
        )

    async def get_post(self, post_id: str) -> SnsPost:
        """피드 게시물을 조회한다. 없으면 SnsPostNotFoundException."""
        self.log.debug("피드 게시물 조회: id=%s", post_id)
        post = await self.repository.get_by_id(post_id)
        if post is None:
            raise SnsPostNotFoundException(detail={"id": post_id})
        return post

    async def list_posts(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[Sequence[SnsPost], int]:
        """피드 게시물 목록과 전체 개수를 조회한다."""
        self.log.debug("피드 게시물 목록 조회: skip=%s limit=%s", skip, limit)
        posts = await self.repository.get_all(skip=skip, limit=limit)
        total = await self.repository.count()
        return posts, total

    async def update_post(self, post_id: str, data: SnsPostUpdate, principal: Principal) -> SnsPost:
        """게시물을 부분 수정한다. 없으면 404, 소유자·슈퍼유저가 아니면 403."""
        self.log.debug("피드 게시물 수정: id=%s", post_id)
        existing = await self.get_post(post_id)  # 존재 보장(없으면 404)
        self.ownership.ensure_can_modify(existing.author_id, principal)
        updated = await self.repository.update(post_id, data.model_dump(exclude_unset=True))
        # updated 가 None 이면 변경행 0(동일 값 no-op, MySQL changed-rows 의미). 존재는 이미
        # 보장됐으므로 404 가 아니라 현재 엔티티를 반환한다.
        return updated if updated is not None else existing

    async def delete_post(self, post_id: str, principal: Principal) -> None:
        """게시물을 삭제한다. 없으면 404, 소유자·슈퍼유저가 아니면 403."""
        self.log.debug("피드 게시물 삭제: id=%s", post_id)
        existing = await self.get_post(post_id)  # 존재 보장(없으면 404)
        self.ownership.ensure_can_modify(existing.author_id, principal)
        deleted = await self.repository.delete(post_id)
        if not deleted:
            raise SnsPostNotFoundException(detail={"id": post_id})
