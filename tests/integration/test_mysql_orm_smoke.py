"""MySQL 8.4 ORM 스모크 — SQLite 가 대신 답할 수 없는 성질 (service-hardening C2).

SQLite 단위 테스트는 같은 코드를 빠르게 돌리지만, 아래 다섯은 **방언이 결정**한다.

1. 대표 ORM 기능(catalog)의 CRUD 가 실제 Service/Repository 로 MySQL 에서 돈다.
2. ``created_at`` 이 같은 행들의 목록 순서가 결정적이고 offset 페이지가 겹치지 않는다
   (``DATETIME`` 은 초 단위라 MySQL 에서 동률이 더 흔하다).
3. username 중복은 ``utf8mb4_unicode_ci`` 로 판정된다 — "Kim" 다음 "kim" 은 **중복**이다.
   SQLite(BINARY 비교)에서는 두 행이 다 들어가므로 여기서만 고정할 수 있다.
4. NOT NULL 컬럼을 ``None`` 으로 UPDATE 하면 strict 모드가 1048 로 거부하고, 변환기가
   422 로 바꾼다.
5. 긴 접속 로그 값은 저장 직전에 컬럼 길이로 잘린다 — 자르지 않으면 strict 모드가
   1406(Data too long)으로 INSERT 를 거부한다.

스키마는 ``mysql_session_maker`` 가 테스트마다 새로 만든다(App Registry 경로, C-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import String, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exception import DuplicateException, ValidationException
from app.features.catalog.exceptions import ProductNotFoundException
from app.features.catalog.models.models import Product
from app.features.catalog.repositories.product_repository import ProductRepository
from app.features.catalog.schemas.product_schema import ProductCreate, ProductUpdate
from app.features.catalog.services.catalog_service import CatalogService
from app.features.home.models.models import UserAccessLog
from app.features.home.services.user_access_log_service import UserAccessLogService
from app.features.user.repositories.user_repository import UserRepository

pytestmark = pytest.mark.mysql


async def _assert_strict_mode(session: AsyncSession) -> None:
    """4·5 번은 strict 모드가 전제다. 꺼져 있으면 경고만 남기고 값을 바꿔 저장한다."""
    sql_mode = await session.scalar(text("SELECT @@SESSION.sql_mode"))
    assert "STRICT_TRANS_TABLES" in sql_mode, f"strict 모드가 아니다: {sql_mode}"


def _max_length(column: str) -> int:
    """접속 로그 컬럼의 선언 길이 — 숫자를 테스트에 다시 적지 않는다."""
    column_type = UserAccessLog.__table__.c[column].type
    assert isinstance(column_type, String) and column_type.length
    return column_type.length


@pytest.mark.asyncio
async def test_catalog_crud_round_trips_through_service(mysql_session_maker):
    async with mysql_session_maker() as session:
        service = CatalogService(session)
        created = await service.create_product(
            ProductCreate(sku="SMOKE-1", name="키보드", price=Decimal("129000.50"), stock=3)
        )
        await session.commit()

    async with mysql_session_maker() as session:
        service = CatalogService(session)
        fetched = await service.get_product(created.id)
        assert (fetched.sku, fetched.price, fetched.stock) == ("SMOKE-1", Decimal("129000.50"), 3)

        updated = await service.update_product(created.id, ProductUpdate(stock=7))
        await session.commit()
        assert updated.stock == 7

        await service.delete_product(created.id)
        await session.commit()

    async with mysql_session_maker() as session:
        with pytest.raises(ProductNotFoundException):
            await CatalogService(session).get_product(created.id)


@pytest.mark.asyncio
async def test_same_created_at_lists_in_a_stable_order(mysql_session_maker):
    """``created_at`` 이 모두 같아도 PK 보조 키로 순서가 고정되고 페이지가 겹치지 않는다."""
    same_moment = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    async with mysql_session_maker() as session:
        repository = ProductRepository(session)
        for index in range(5):
            await repository.create(
                {
                    "sku": f"TIE-{index}",
                    "name": f"동률 {index}",
                    "price": Decimal("1.00"),
                    "created_at": same_moment,
                    "updated_at": same_moment,
                }
            )
        await session.commit()

    async with mysql_session_maker() as session:
        service = CatalogService(session)
        pages = [(await service.list_products(skip=skip, limit=2))[0] for skip in (0, 2, 4)]
        listed = [product.id for page in pages for product in page]
        # 기대 순서는 DB 자신의 콜레이션으로 정렬한 PK 역순이다(created_at 은 모두 같다).
        expected = list(
            (await session.scalars(select(Product.id).order_by(Product.id.desc()))).all()
        )
        again = [p.id for p in (await service.list_products(skip=0, limit=5))[0]]

    assert len(listed) == len(set(listed)) == 5, f"offset 페이지가 겹치거나 빠졌다: {listed}"
    assert listed == expected
    assert again == expected, "같은 질의가 다른 순서를 돌려준다"


@pytest.mark.asyncio
async def test_username_duplicate_is_case_insensitive(mysql_session_maker):
    """utf8mb4_unicode_ci 에서 "Kim" 과 "kim" 은 같은 값이다 → 1062 → 409."""
    async with mysql_session_maker() as session:
        collation = await session.scalar(
            text(
                "SELECT COLLATION_NAME FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'users' "
                "AND COLUMN_NAME = 'username'"
            )
        )
        assert collation == "utf8mb4_unicode_ci"

        repository = UserRepository(session)
        await repository.create({"username": "Kim", "email": "kim@example.com"})
        await session.commit()

        with pytest.raises(DuplicateException) as excinfo:
            await repository.create({"username": "kim", "email": "kim2@example.com"})
        assert excinfo.value.status_code == 409
        await session.rollback()

        # 조회도 같은 콜레이션을 따른다 — 서비스의 사전 중복 검사가 대소문자를 넘어 잡는다.
        found = await repository.get_by_username("KIM")
        assert found is not None and found.username == "Kim"


@pytest.mark.asyncio
async def test_null_on_not_null_column_is_a_422(mysql_session_maker):
    """``repository.update`` 로 NOT NULL 컬럼에 None → 1048 → ValidationException(422)."""
    async with mysql_session_maker() as session:
        await _assert_strict_mode(session)
        repository = ProductRepository(session)
        product_id = (await repository.create({"sku": "NN-1", "name": "원래 이름", "price": 1})).id
        await session.commit()

        with pytest.raises(ValidationException) as excinfo:
            await repository.update(product_id, {"name": None})
        assert excinfo.value.status_code == 422
        await session.rollback()

    async with mysql_session_maker() as session:
        kept = await session.scalar(select(Product.name).where(Product.id == product_id))
    assert kept == "원래 이름"


@pytest.mark.asyncio
async def test_long_access_log_values_are_truncated_and_stored(mysql_session_maker):
    """헤더 길이는 클라이언트가 정한다 — 컬럼보다 길어도 기록은 남는다(잘려서)."""
    async with mysql_session_maker() as session:
        await _assert_strict_mode(session)
        log = await UserAccessLogService(session).create_access_log(
            {
                "ip_address": "203.0.113.7",
                "request_path": "/" + "p" * 5000,
                "request_method": "GET",
                "os_name": "o" * 500,
                "accept_language": "가" * 1000,
                "session_id": "s" * 400,
                "is_bot": False,
            }
        )
        await session.commit()

    async with mysql_session_maker() as session:
        stored = await session.get(UserAccessLog, log.id)

    assert stored is not None
    assert stored.request_path == ("/" + "p" * 5000)[: _max_length("request_path")]
    assert stored.os_name == "o" * _max_length("os_name")
    assert stored.accept_language == "가" * _max_length("accept_language")
    assert stored.session_id == "s" * _max_length("session_id")
