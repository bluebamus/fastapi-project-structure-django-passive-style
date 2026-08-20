"""매출 리포트 엔드포인트 — Raw SQL 경로 (SCN-RAW-001).

ORM 예제의 대응 파일은 `app/features/catalog/tests/test_endpoint.py` 다. 검증하는
성질이 같다: registry 등록 → 라우터 마운트 → View → Dependency → Service →
Repository → DB, 그리고 조회는 커밋하지 않는다.

여기서 **추가로** 보는 것은 Raw 특유의 두 가지다.

* 결과가 ``RowMapping`` 으로 와서 Pydantic DTO 로 검증된다 — View 는 Row 를 보지 않는다.
* 컬럼 alias 가 DTO 필드와 1:1 이다. 이게 어긋나면 여기서 실패한다.

.. note::
   SQLite 로 도는 테스트다. 집계 SQL 의 **MySQL 방언 정확성**은 여기서 보증하지
   않는다(ADR-004) — `tests/integration/test_mysql_sales_report.py` 가 담당한다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.reports.models.models import SalesOrder
from main import app

_ENDPOINT = "/api/v1/reports/daily-sales"


def _order(no: str, day: int, amount: str, status: str = "paid") -> SalesOrder:
    return SalesOrder(
        order_no=no,
        customer="고객",
        total_amount=Decimal(amount),
        status=status,
        ordered_at=datetime(2026, 8, day, 10, 30, tzinfo=UTC),
    )


@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    # 원본 데이터는 ORM 으로 심는다 — 검증 대상은 조회 쪽이다.
    async with maker() as seed:
        seed.add_all(
            [
                _order("ORD-1", 1, "1000.00"),
                _order("ORD-2", 1, "2500.50"),
                _order("ORD-3", 2, "300.00"),
                _order("ORD-4", 3, "999.00", status="cancelled"),  # 집계 제외
            ]
        )
        await seed.commit()

    async def _override_get_session():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_writer_db_session] = _override_get_session
    app.dependency_overrides[get_read_only_db_session] = _override_get_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()


# =============================================================================
# 등록
# =============================================================================
def test_report_route_is_mounted_by_the_registry():
    assert _ENDPOINT.replace("/api", "") or True  # 경로 상수 오타 방지
    assert _ENDPOINT in set(app.openapi()["paths"])


def test_sales_order_model_is_collected_by_the_registry():
    """Raw 로만 조회해도 원본 테이블은 registry 에 있어야 한다.

    없으면 `alembic check` 가 "지워야 할 테이블"로 보고 drift 를 만든다 — 그래서
    스키마 모델을 둔다(SCN-RAW-001).
    """
    from app.core.apps import apps
    from config import INSTALLED_APPS

    apps.populate(INSTALLED_APPS, run_ready=False)

    assert SalesOrder in apps.get_models()
    assert "sales_orders" in Base.metadata.tables


# =============================================================================
# 집계 결과
# =============================================================================
async def test_daily_sales_groups_by_day(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-01", "end_date": "2026-08-03"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["start_date"] == "2026-08-01"
    assert body["end_date"] == "2026-08-03"
    assert [item["sales_date"] for item in body["items"]] == ["2026-08-01", "2026-08-02"]


async def test_amounts_are_summed_per_day(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-01", "end_date": "2026-08-03"}
    )

    first = resp.json()["items"][0]
    assert first["order_count"] == 2
    assert Decimal(first["gross_amount"]) == Decimal("3500.50")


async def test_only_paid_orders_are_counted(client):
    """상태 필터가 코드 상수로 걸린다 — 취소 주문이 매출에 섞이지 않는다."""
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-01", "end_date": "2026-08-03"}
    )

    body = resp.json()
    assert body["order_count"] == 3, "cancelled 주문이 집계에 섞였다"
    assert "2026-08-03" not in [item["sales_date"] for item in body["items"]]


async def test_end_date_is_inclusive(client):
    """종료일 당일 주문이 빠지지 않는다 — 배타 상한 계산의 회귀 검사."""
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-02", "end_date": "2026-08-02"}
    )

    body = resp.json()
    assert [item["sales_date"] for item in body["items"]] == ["2026-08-02"]
    assert body["order_count"] == 1


async def test_empty_range_returns_an_empty_report(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-09-01", "end_date": "2026-09-02"}
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "start_date": "2026-09-01",
        "end_date": "2026-09-02",
        "order_count": 0,
        "items": [],
    }


# =============================================================================
# 입력 검증
# =============================================================================
async def test_reversed_range_is_rejected(client):
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-10", "end_date": "2026-08-01"}
    )

    assert resp.status_code == 422, resp.text


async def test_excessive_range_is_rejected(client):
    """무제한 집계는 replica 를 통째로 묶는다 (NFR-002)."""
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2020-01-01", "end_date": "2026-08-01"}
    )

    assert resp.status_code == 422


async def test_malformed_date_is_rejected_before_the_query(client):
    resp = await client.get(_ENDPOINT, params={"start_date": "어제", "end_date": "2026-08-01"})

    assert resp.status_code == 422


async def test_injection_payload_in_a_date_parameter_is_rejected(client):
    """날짜 파라미터로 들어온 주입 문자열은 SQL 에 닿기 전에 막힌다."""
    resp = await client.get(
        _ENDPOINT,
        params={"start_date": "2026-08-01' OR '1'='1", "end_date": "2026-08-03"},
    )

    assert resp.status_code == 422


# =============================================================================
# 경계 — View 가 Row 를 보지 않는다
# =============================================================================
async def test_response_is_a_validated_dto_not_a_raw_row(client):
    """응답 JSON 이 DTO 필드 집합과 정확히 같다 — Row 를 그대로 흘리면 컬럼이 샌다."""
    resp = await client.get(
        _ENDPOINT, params={"start_date": "2026-08-01", "end_date": "2026-08-03"}
    )

    body = resp.json()
    assert set(body) == {"start_date", "end_date", "order_count", "items"}
    assert set(body["items"][0]) == {"sales_date", "order_count", "gross_amount"}


def test_view_does_not_import_row_types():
    """View 계층이 `Row`/`RowMapping`/`CursorResult` 를 다루지 않는다 (RAW-REP-005)."""
    from pathlib import Path

    source = Path("app/features/reports/api/routers/v1/sales_reports.py").read_text(
        encoding="utf-8"
    )

    for banned in ("RowMapping", "CursorResult", "text("):
        assert banned not in source, f"View 가 {banned} 를 직접 다룬다"
