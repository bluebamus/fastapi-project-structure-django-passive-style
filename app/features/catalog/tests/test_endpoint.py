"""Catalog 상품 CRUD 엔드포인트 (SCN-ORM-001).

registry 등록 → 라우터 마운트 → View → Dependency → Service → Repository → DB 의
전체 경로를 in-memory SQLite 로 검증한다.

Raw 예제의 대응 파일은 `app/features/reports/tests/test_endpoint.py` 다. 두 파일이
같은 모양이라는 것이 이 Phase 의 결과물이다 — 데이터 접근 방식이 달라도 HTTP 계약과
테스트 구조는 같다.
"""

from __future__ import annotations

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session
from app.features.catalog.models.models import Product  # noqa: F401  (register table)
from main import app

_NEW = {
    "sku": "SKU-1001",
    "name": "기계식 키보드",
    "description": "적축 87키",
    "price": "129000.00",
    "stock": 25,
    "is_active": True,
}
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


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

    async def _override_get_session():
        async with maker() as session:
            yield session

    # 조회는 read-only Dependency 를 쓴다 — 함께 오버라이드하지 않으면 읽기 경로가
    # 실제 MySQL 로 새어나간다.
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
def test_catalog_routes_are_mounted_by_the_registry():
    """`INSTALLED_APPS` 등록만으로 라우터가 붙는다 — main.py 는 건드리지 않았다."""
    paths = set(app.openapi()["paths"])

    assert "/api/v1/catalog/products" in paths
    assert "/api/v1/catalog/products/{product_id}" in paths


def test_product_model_is_collected_by_the_registry():
    """migration 과 runtime 이 같은 모델 집합을 본다(C-3)."""
    from app.core.apps import apps
    from config import INSTALLED_APPS

    apps.populate(INSTALLED_APPS, run_ready=False)

    assert Product in apps.get_models()
    assert "catalog_products" in Base.metadata.tables


# =============================================================================
# CRUD
# =============================================================================
async def test_create_and_get_product(client):
    created = await client.post("/api/v1/catalog/products", json=_NEW)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["sku"] == "SKU-1001"
    assert body["price"] == "129000.00", "Decimal 이 float 으로 뭉개지면 합계가 틀어진다"
    assert body["id"]

    fetched = await client.get(f"/api/v1/catalog/products/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


async def test_duplicate_sku_is_a_conflict(client):
    await client.post("/api/v1/catalog/products", json=_NEW)

    duplicate = await client.post("/api/v1/catalog/products", json=_NEW)

    assert duplicate.status_code == 409, duplicate.text
    assert "SKU-1001" not in duplicate.text, "중복 응답에 입력값이 그대로 되돌아온다"


async def test_list_is_paginated_and_stable(client):
    for index in range(3):
        payload = {**_NEW, "sku": f"SKU-200{2 - index}"}  # 역순으로 넣는다
        assert (await client.post("/api/v1/catalog/products", json=payload)).status_code == 201

    listed = await client.get("/api/v1/catalog/products", params={"skip": 0, "limit": 2})

    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["limit"] == 2


async def test_list_rejects_an_unbounded_limit(client):
    """무제한 조회를 허용하지 않는다 (NFR-002)."""
    assert (await client.get("/api/v1/catalog/products?limit=1000")).status_code == 422


async def test_active_only_filter_uses_the_domain_query(client):
    await client.post("/api/v1/catalog/products", json={**_NEW, "sku": "SKU-ON"})
    await client.post(
        "/api/v1/catalog/products", json={**_NEW, "sku": "SKU-OFF", "is_active": False}
    )

    listed = await client.get("/api/v1/catalog/products", params={"active_only": True})

    skus = [item["sku"] for item in listed.json()["items"]]
    assert skus == ["SKU-ON"]


async def test_partial_update_touches_only_the_given_fields(client):
    created = (await client.post("/api/v1/catalog/products", json=_NEW)).json()

    updated = await client.patch(f"/api/v1/catalog/products/{created['id']}", json={"stock": 3})

    assert updated.status_code == 200
    body = updated.json()
    assert body["stock"] == 3
    assert body["name"] == _NEW["name"], "전달하지 않은 필드가 덮어써졌다"


async def test_delete_removes_the_product(client):
    created = (await client.post("/api/v1/catalog/products", json=_NEW)).json()

    assert (await client.delete(f"/api/v1/catalog/products/{created['id']}")).status_code == 204
    assert (await client.get(f"/api/v1/catalog/products/{created['id']}")).status_code == 404


# =============================================================================
# 오류
# =============================================================================
async def test_missing_product_is_404(client):
    assert (await client.get(f"/api/v1/catalog/products/{_MISSING_ID}")).status_code == 404
    assert (
        await client.patch(f"/api/v1/catalog/products/{_MISSING_ID}", json={"stock": 1})
    ).status_code == 404
    assert (await client.delete(f"/api/v1/catalog/products/{_MISSING_ID}")).status_code == 404


async def test_invalid_payload_is_422(client):
    bad = await client.post("/api/v1/catalog/products", json={**_NEW, "price": "-1"})

    assert bad.status_code == 422


async def test_error_response_carries_no_sql(client):
    """오류 응답에 SQL 본문·bind 값이 실리지 않는다 (C-12)."""
    await client.post("/api/v1/catalog/products", json=_NEW)

    conflict = await client.post("/api/v1/catalog/products", json=_NEW)

    text = conflict.text
    for leaked in ("INSERT INTO", "catalog_products", "sqlite", "SELECT"):
        assert leaked not in text, f"오류 응답에 '{leaked}' 가 노출됐다: {text}"
