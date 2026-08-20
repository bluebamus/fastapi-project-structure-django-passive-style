"""MySQL 8.4 통합 하네스 자체가 동작하는지 (development-plan §10.1 C · ADR-004).

Phase 5 의 Raw SQL 시나리오 테스트가 여기 올라온다. 그 전에 **하네스가 실제로
MySQL 에 붙어 스키마를 만든다**는 것부터 확인한다 — conftest 가 조용히 잘못돼 있으면
나중에 추가되는 방언 테스트 전부가 근거를 잃는다.

C-3(migration 과 runtime 이 같은 registry 모델 집합을 쓴다)을 MySQL 위에서 본다.
SQLite 로는 검증되지 않는다: 타입 매핑도 DDL 도 방언마다 다르다.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.mysql


@pytest.mark.asyncio
async def test_registry_metadata_creates_schema_on_mysql(mysql_session_maker):
    """App Registry 가 채운 metadata 로 MySQL 에 실제 테이블이 생긴다."""
    async with mysql_session_maker() as session:
        tables = (await session.execute(text("SHOW TABLES"))).scalars().all()

    assert (
        tables
    ), "registry metadata 로 만든 테이블이 하나도 없습니다 — populate 경로를 확인하세요."


@pytest.mark.asyncio
async def test_mysql_dialect_is_really_mysql(mysql_session_maker):
    """SQLite 로 조용히 대체되지 않았는지 — 방언 승인의 전제다."""
    async with mysql_session_maker() as session:
        version = (await session.execute(text("SELECT VERSION()"))).scalar_one()
        charset = (await session.execute(text("SELECT @@character_set_server"))).scalar_one()

    assert version.startswith("8.4"), f"MySQL 8.4 가 아닙니다: {version}"
    assert charset == "utf8mb4", f"utf8mb4 가 아닙니다: {charset}"
