"""MySQL 방언 확인 — 접속 로그 보존 삭제의 배치 쿼리 (security-ops-hardening ADR-002).

SQLite 단위 테스트(``app/features/home/tests/test_access_log_retention.py``)와 **같은 쿼리**가
MySQL 8.4 에서도 도는지 본다. MySQL 은 같은 테이블의 ``IN (SELECT ... LIMIT)`` 을 거부하므로
(ER_NOT_SUPPORTED_YET) 저장소는 id 를 먼저 ``LIMIT`` 으로 고른 뒤 지운다. 그 결과 배치 경계와
``DATETIME(6)`` 의 마이크로초 경계가 SQLite 와 같아야 한다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import UserAccessLogService

pytestmark = pytest.mark.mysql

NOW = datetime(2026, 10, 19, 3, 30, tzinfo=UTC)


@pytest.mark.asyncio
async def test_batched_purge_on_mysql_keeps_the_boundary_row(mysql_session_maker):
    cutoff = NOW - timedelta(days=30)
    old = [cutoff - timedelta(minutes=i + 1) for i in range(5)]
    old.append(cutoff - timedelta(microseconds=1))
    async with mysql_session_maker() as session:
        session.add_all(
            UserAccessLog(
                ip_address="10.0.0.1", request_path=f"/p{i}", request_method="GET", created_at=at
            )
            for i, at in enumerate([*old, cutoff, NOW])
        )
        await session.commit()

        deleted = await UserAccessLogService(session, retention_days=30).purge_expired(
            now=NOW, batch_size=4
        )

        assert deleted == len(old)
        remaining = await session.scalar(select(func.count()).select_from(UserAccessLog))
        assert remaining == 2, "정확히 N일 전 행과 보존 기간 안의 행만 남아야 한다"
