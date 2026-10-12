"""리포트의 영업일은 설정 시간대 기준이다 (service-hardening 단계 D3 · ADR-010).

DB 는 UTC 로 저장한다. 그래서 입력 날짜(지역 일자)를 UTC 순간으로 바꿔 조회하고, 일자
버킷은 UTC 값을 지역 오프셋만큼 옮긴 날짜다. 2026-01-01T15:30Z 주문은 Asia/Seoul 로
1월 2일 00:30 이므로 **1월 2일** 매출이다.

MySQL 의 ``CONVERT_TZ`` 버킷은 ``tests/integration/test_mysql_time_policy.py`` 가 본다.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.features.reports.dependencies import reports_dependencies
from app.features.reports.models.models import SalesOrder
from app.features.reports.repositories.sales_report_repository import mysql_offset
from app.features.reports.services.report_service import ReportService
from config import TimezoneSettings
from main import app
from tests.session_overrides import sqlite_session_overrides

_ENDPOINT = "/api/v1/reports/daily-sales"
SEOUL = TimezoneSettings(TIME_ZONE="Asia/Seoul")


class _RecordingRepository:
    """Service 가 Repository 에 넘기는 경계를 기록한다."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def daily_sales(self, **kwargs):
        self.calls.append(kwargs)
        return []

    async def order_count(self, **kwargs):
        self.calls.append(kwargs)
        return 0


async def test_local_dates_become_utc_bounds_and_offset():
    service = ReportService(session=None, timezone=SEOUL)  # type: ignore[arg-type]
    service.repository = _RecordingRepository()  # type: ignore[assignment]

    await service.daily_sales_report(start_date=date(2026, 1, 2), end_date=date(2026, 1, 2))

    daily, count = service.repository.calls
    assert daily == {
        "start_at": datetime(2026, 1, 1, 15, 0, tzinfo=UTC),
        "end_exclusive": datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
        "utc_offset": timedelta(hours=9),
    }
    assert count == {
        "start_at": datetime(2026, 1, 1, 15, 0, tzinfo=UTC),
        "end_exclusive": datetime(2026, 1, 2, 15, 0, tzinfo=UTC),
    }


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (timedelta(hours=9), "+09:00"),
        (timedelta(0), "+00:00"),
        (timedelta(hours=-3, minutes=-30), "-03:30"),
        (timedelta(hours=5, minutes=45), "+05:45"),
    ],
)
def test_mysql_offset_text(offset, expected):
    assert mysql_offset(offset) == expected


@pytest_asyncio.fixture
async def client(monkeypatch):
    # 로컬 .env 의 TIME_ZONE 과 무관하게 Asia/Seoul 로 판정한다.
    monkeypatch.setattr(reports_dependencies, "timezone_settings", SEOUL)
    async with sqlite_session_overrides(app) as maker:
        async with maker() as seed:
            seed.add_all(
                [
                    SalesOrder(
                        order_no=order_no,
                        customer="고객",
                        total_amount=Decimal("100.00"),
                        status="paid",
                        ordered_at=ordered_at,
                    )
                    for order_no, ordered_at in (
                        # 1월 1일 23:59:59.999999 KST — 1월 1일
                        ("ORD-A", datetime(2026, 1, 1, 14, 59, 59, 999999, tzinfo=UTC)),
                        # 1월 2일 00:30 KST — UTC 로는 1월 1일이지만 1월 2일 매출이다
                        ("ORD-B", datetime(2026, 1, 1, 15, 30, tzinfo=UTC)),
                        # 1월 3일 00:00 KST — 1월 3일
                        ("ORD-C", datetime(2026, 1, 2, 15, 0, tzinfo=UTC)),
                    )
                ]
            )
            await seed.commit()

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_order_after_local_midnight_counts_for_the_next_local_day(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-01-02", "end_date": "2026-01-02"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["order_count"] == 1
    assert [(i["sales_date"], i["order_count"]) for i in body["items"]] == [("2026-01-02", 1)]


async def test_each_order_lands_on_its_local_day(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-01-01", "end_date": "2026-01-03"}
    )

    assert resp.status_code == 200, resp.text
    assert [(i["sales_date"], i["order_count"]) for i in resp.json()["items"]] == [
        ("2026-01-01", 1),
        ("2026-01-02", 1),
        ("2026-01-03", 1),
    ]
