"""
기본 Repository 클래스

모든 Repository의 기반이 되는 Generic 클래스입니다.
CRUD 작업과 N+1 문제 해결을 위한 Eager Loading 메서드를 제공합니다.

사용법:
    class UserRepository(BaseRepository[User]):
        model = User

    # 기본 CRUD
    user = await repo.create({"name": "John"})
    user = await repo.get_by_id("id")
    users = await repo.get_all()

    # N+1 해결 - Eager Loading
    user = await repo.get_by_id_with("id", relations=["posts", "profile"])
    users = await repo.get_all_with(relations=["posts"])
"""

from collections.abc import Sequence
from typing import Any, cast
from uuid import uuid4

from sqlalchemy import CursorResult, delete, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.errors import convert_db_error
from app.core.repositories.crud_base import CRUDBase, ModelType, PrimaryKeyT
from app.utils.logs import get_logger

logger = get_logger("repository")


class BaseRepository(CRUDBase[ModelType, PrimaryKeyT]):
    """
    기본 Repository 클래스

    SQLAlchemy 모델에 대한 CRUD 작업과 N+1 문제 해결을 위한
    Eager Loading 메서드를 제공합니다.

    Attributes:
        model: SQLAlchemy 모델 클래스 (하위 클래스에서 정의)
        session: 비동기 데이터베이스 세션

    Type Parameters:
        ModelType: Base를 상속한 SQLAlchemy 모델 타입
        PrimaryKeyT: 기본키 타입 (기본값 ``str``)

    Example:
        class UserRepository(BaseRepository[User]):
            model = User

        repo = UserRepository(session)
        user = await repo.get_by_id("123")  # 타입: User | None
    """

    model: type[ModelType]

    def __init__(self, session: AsyncSession) -> None:
        """
        BaseRepository 초기화

        Args:
            session: 비동기 데이터베이스 세션 (AsyncSession)
        """
        super().__init__(session)

    # ========================================================================
    # LOADING STRATEGY HELPERS (내부 헬퍼 메서드)
    # ========================================================================

    # ========================================================================
    # CREATE (생성)
    # ========================================================================

    async def create(self, data: dict[str, Any]) -> ModelType:
        """
        새로운 레코드를 생성합니다.

        Args:
            data: 생성할 데이터 딕셔너리

        Returns:
            생성된 모델 인스턴스

        Raises:
            DuplicateException: 중복 데이터가 존재하는 경우
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.create({"name": "John", "email": "john@example.com"})
        """
        if "id" not in data:
            data["id"] = str(uuid4())

        try:
            instance = self.model(**data)
            return await self._add(instance)  # CRUDBase 메서드 활용
        except SQLAlchemyError as exc:
            raise convert_db_error(exc, operation="CREATE", model=self.model.__name__) from None

    # ========================================================================
    # READ - 기본 조회
    # ========================================================================

    async def get_by_id(self, id: PrimaryKeyT) -> ModelType | None:
        """
        ID로 레코드를 조회합니다.

        Args:
            id: 조회할 레코드의 ID

        Returns:
            모델 인스턴스 또는 None

        Example:
            user = await repo.get_by_id("550e8400-e29b-41d4-a716-446655440000")
        """
        return await self._get(id)  # CRUDBase 메서드 활용

    async def get_one(self, **filters: Any) -> ModelType | None:
        """
        필터 조건으로 단일 레코드를 조회합니다.

        Args:
            **filters: 필터 조건 (컬럼명=값)

        Returns:
            모델 인스턴스 또는 None

        Example:
            user = await repo.get_one(email="john@example.com")
        """
        stmt = select(self.model).filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ModelType]:
        """
        모든 레코드를 조회합니다.

        Args:
            skip: 건너뛸 레코드 수
            limit: 최대 조회 수

        Returns:
            모델 인스턴스 목록

        Example:
            users = await repo.get_all(skip=0, limit=100)
        """
        stmt = select(self.model).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self, **filters: Any) -> int:
        """
        레코드 수를 반환합니다.

        Args:
            **filters: 필터 조건 (선택적)

        Returns:
            레코드 수

        Example:
            total = await repo.count()
            active_count = await repo.count(is_active=True)
        """
        stmt = select(func.count()).select_from(self.model)
        if filters:
            stmt = stmt.filter_by(**filters)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def exists(self, id: PrimaryKeyT) -> bool:
        """
        ID로 레코드 존재 여부를 확인합니다.

        Args:
            id: 확인할 레코드의 ID

        Returns:
            존재 여부 (True/False)

        Example:
            if await repo.exists("user-123"):
                print("User exists")
        """
        stmt = select(func.count()).select_from(self.model).where(self.model.id == id)
        result = await self.session.execute(stmt)
        return result.scalar_one() > 0

    # ========================================================================
    # READ - Eager Loading (N+1 문제 해결)
    # ========================================================================

    # ========================================================================
    # READ - Partial Loading (컬럼 최적화)
    # ========================================================================

    # ========================================================================
    # READ - Batch Loading (배치 처리)
    # ========================================================================

    # ========================================================================
    # READ - Join (명시적 조인)
    # ========================================================================

    # ========================================================================
    # READ - Aggregation (집계)
    # ========================================================================

    # ========================================================================
    # UPDATE (수정)
    # ========================================================================

    async def update(self, id: PrimaryKeyT, data: dict[str, Any]) -> ModelType | None:
        """
        ID로 레코드를 업데이트합니다.

        Args:
            id: 업데이트할 레코드의 ID
            data: 업데이트할 데이터 딕셔너리

        Returns:
            업데이트된 모델 인스턴스 또는 None

        Raises:
            DuplicateException: 중복 데이터로 인한 제약 조건 위반
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            user = await repo.update("user-123", {"name": "New Name"})
        """
        try:
            stmt = update(self.model).where(self.model.id == id).values(**data)
            await self.session.execute(stmt)
            await self.session.flush()

            # rowcount 0 을 "행이 없다"로 읽으면 안 된다. MySQL 은 UPDATE 로 **값이
            # 바뀐** 행 수를 돌려주므로, 같은 값으로 덮어쓰는 no-op PATCH 는 행이
            # 멀쩡히 있어도 0 이다. 그대로 None 을 반환하면 존재하는 리소스가 404 가
            # 된다. 존재 여부는 조회로 판단한다 — 없으면 None, 있으면 그대로 돌려준다.
            return await self.get_by_id(id)
        except SQLAlchemyError as exc:
            raise convert_db_error(
                exc, operation="UPDATE", model=self.model.__name__, id=id
            ) from None

    # ========================================================================
    # DELETE (삭제)
    # ========================================================================

    async def delete(self, id: PrimaryKeyT) -> bool:
        """
        ID로 레코드를 삭제합니다.

        Args:
            id: 삭제할 레코드의 ID

        Returns:
            삭제 성공 여부 (True/False)

        Raises:
            DatabaseException: 데이터베이스 오류가 발생한 경우

        Example:
            if await repo.delete("user-123"):
                print("User deleted")
        """
        try:
            stmt = delete(self.model).where(self.model.id == id)
            result = cast("CursorResult[Any]", await self.session.execute(stmt))
            await self.session.flush()
            return result.rowcount > 0
        except SQLAlchemyError as exc:
            raise convert_db_error(
                exc, operation="DELETE", model=self.model.__name__, id=id
            ) from None

    # ========================================================================
    # UPSERT (생성 또는 수정)
    # ========================================================================
