"""Reports 기능 의존성.

**조회 전용 기능이라 read-only 세션만 노출한다.** Raw SQL 이라는 이유로 쓰기 세션을
쓰지 않는다 — 세션 선택은 데이터 접근 방식이 아니라 **하는 일**이 결정한다.

read-only 세션에서 Raw DML 을 시도하면 실행 전에 거부된다(ADR-017). 그 동작은
`tests/test_raw_dml_workflow.py` 가 고정한다.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_read_only_db_session
from app.features.reports.services.report_service import ReportService


async def get_report_service_readonly(
    session: AsyncSession = Depends(get_read_only_db_session),
) -> ReportService:
    """조회용 — 커밋하지 않는다."""
    return ReportService(session)
