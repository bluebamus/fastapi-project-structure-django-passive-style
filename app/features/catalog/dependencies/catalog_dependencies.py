"""Catalog 기능 의존성.

Service 를 세션과 결합해 View 에 제공한다. **읽기와 쓰기가 다른 세션을 받는다** —
조회는 read-only(replica 가능), 쓰기는 writer 고정이다(C-1·C-17).

Raw 예제(`reports`)의 dependencies 와 구조가 같다. 데이터 접근 방식이 달라도
세션 선택 규칙은 공통이라는 것이 ADR-002 의 내용이다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session, get_writer_db_session
from app.features.catalog.services.catalog_service import CatalogService


async def get_catalog_service(
    session: AsyncSession = Depends(get_writer_db_session),
) -> CatalogService:
    """쓰기용 — 커밋은 View 본문이 한다(ADR-008)."""
    return CatalogService(session)


async def get_catalog_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> CatalogService:
    """조회용 — 커밋하지 않는다. 쓰기를 시도하면 실행 전에 거부된다."""
    return CatalogService(session)
