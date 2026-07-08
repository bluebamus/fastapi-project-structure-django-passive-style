"""페이지네이션 유틸리티.

범용 페이지네이션을 두 조각으로 제공한다.

- ``PaginatedResponse`` : 반환 데이터 타입을 고정하는 **데이터클래스**(컨테이너).
  ``return cls()`` 로 생성될 필드만 정의하며, 각 필드는 초기값을 갖는다.
- ``Paginator`` : SQLAlchemy 모델을 페이지네이션 조회하는 **인스턴스화 가능한 실행기**.

사용 예시:
    from app.utils.pagination import Paginator, PaginatedResponse

    paginator = Paginator(session, User, UserItem)
    result: PaginatedResponse[UserItem] = await paginator.paginate(page=1, page_size=20)

    # 커스텀 변환
    result = await paginator.paginate(
        page=1,
        transform_fn=lambda u: UserItem(id=u.id, username=u.username),
    )

Note:
    ``PaginatedResponse`` 는 프레임워크 무관 표준 dataclass 이다. FastAPI 응답으로
    직접 노출하려면 라우터 경계에서 Pydantic 스키마로 변환해 사용한다.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.models.models_base import Base

T = TypeVar("T", bound=BaseModel)
ModelT = TypeVar("ModelT", bound=Base)


@dataclass
class PaginatedResponse(Generic[T]):
    """페이지네이션 응답 컨테이너(반환 타입 고정용 데이터클래스).

    ``create()`` 의 ``return cls()`` 로 채워질 필드만 정의한다. 모든 필드는
    초기값을 가지므로 부분 생성도 가능하지만, 정상 생성은 ``create()`` 를 쓴다.

    Fields:
        items: 현재 페이지 데이터 목록
        total: 전체 데이터 수
        page: 현재 페이지(1부터)
        page_size: 페이지당 데이터 수
        total_pages: 전체 페이지 수
        has_next: 다음 페이지 존재 여부
        has_prev: 이전 페이지 존재 여부
    """

    items: list[T] = field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 1
    has_next: bool = False
    has_prev: bool = False

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[T]:
        """페이지 메타데이터를 계산해 응답을 생성한다."""
        total_pages = math.ceil(total / page_size) if total > 0 and page_size > 0 else 1
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        )


class Paginator(Generic[ModelT, T]):
    """SQLAlchemy 모델을 페이지네이션 조회하는 실행기(재사용 가능, 인스턴스화).

    한 번 구성해두고 여러 페이지 요청에 재사용한다.

    Args:
        session: SQLAlchemy AsyncSession
        model: 조회 대상 SQLAlchemy 모델 클래스
        item_schema: 항목 변환용 Pydantic 스키마 클래스
        max_page_size: 허용 최대 페이지 크기(과도한 요청 방지)
    """

    def __init__(
        self,
        session: AsyncSession,
        model: type[ModelT],
        item_schema: type[T],
        *,
        max_page_size: int = 100,
    ) -> None:
        self.session = session
        self.model = model
        self.item_schema = item_schema
        self.max_page_size = max_page_size

    async def paginate(
        self,
        page: int = 1,
        page_size: int = 20,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = "created_at",
        order_desc: bool = True,
        transform_fn: Callable[[ModelT], T] | None = None,
    ) -> PaginatedResponse[T]:
        """지정 페이지를 조회해 ``PaginatedResponse`` 로 반환한다.

        Args:
            page: 페이지 번호(1부터). 1 미만은 1로 보정.
            page_size: 페이지당 수. [1, max_page_size] 로 보정.
            filters: {컬럼명: 값} 동등 필터(값이 None 이거나 없는 컬럼은 무시).
            order_by: 정렬 컬럼명(모델에 없으면 정렬 생략).
            order_desc: 내림차순 여부.
            transform_fn: 모델→스키마 변환 함수(없으면 필드명 매칭 자동 변환).
        """
        page = max(page, 1)
        page_size = min(max(page_size, 1), self.max_page_size)
        offset = (page - 1) * page_size

        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        if filters:
            for field_name, value in filters.items():
                if value is not None and hasattr(self.model, field_name):
                    column = getattr(self.model, field_name)
                    query = query.where(column == value)
                    count_query = count_query.where(column == value)

        total = int((await self.session.execute(count_query)).scalar() or 0)

        if order_by and hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            query = query.order_by(order_column.desc() if order_desc else order_column.asc())

        query = query.offset(offset).limit(page_size)
        records = list((await self.session.execute(query)).scalars().all())

        if transform_fn is not None:
            items = [transform_fn(record) for record in records]
        else:
            items = [self._to_schema(record) for record in records]

        return PaginatedResponse.create(items=items, total=total, page=page, page_size=page_size)

    def _to_schema(self, record: ModelT) -> T:
        """모델 인스턴스를 스키마 필드명 기준으로 자동 변환한다."""
        data = {
            name: getattr(record, name)
            for name in self.item_schema.model_fields
            if hasattr(record, name)
        }
        return self.item_schema(**data)
