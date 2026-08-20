"""매출 리포트 Repository — **Raw SQL 데이터 접근**.

ORM 대응물은 `app/features/catalog/repositories/product_repository.py` 다. 두 파일이
이 프로젝트에서 ORM 과 Raw 가 갈리는 **유일한 지점**이다.

규칙 셋을 지킨다.

1. 외부 값은 전부 named bind parameter (``:start_date``). 문자열 보간 금지 —
   AST 검사가 f-string·``%``·``.format()``·문자열 연결을 실패시킨다.
2. ``query_name`` 은 코드 상수. 요청값으로 만들지 않는다(ADR-018).
3. 결과는 ``RowMapping``. Service 가 Pydantic 으로 검증해서야 밖으로 나간다.

방언 주의:
    ``DATE()`` 는 MySQL·SQLite 모두 있다. 기간 상한은 ``DATE_ADD(:end, INTERVAL 1 DAY)``
    같은 MySQL 전용 함수 대신 **Service 가 계산한 배타 상한**(``:end_exclusive``)을
    바인딩한다. 테스트 편의로 SQL 을 치환한 것이 아니라, 방언 함수를 계약에서
    빼면 같은 SQL 이 두 DB 에서 그대로 돈다.

    다만 SQLite 와 MySQL 은 **반환 타입**이 다르다 — ``sales_date`` 가 각각 문자열과
    ``date``, ``gross_amount`` 가 float 과 ``Decimal`` 이다. 그래서 결과를 dict 로
    그냥 흘리지 않고 Pydantic 으로 검증한다. 실제 값 정확성은 MySQL 통합
    테스트가 승인한다(ADR-004).
"""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import RowMapping, text

from app.core.repositories.raw_repository_base import RawRepositoryBase

#: 로그 라벨. `feature.use_case` 형식의 코드 상수여야 한다(ADR-018).
QUERY_DAILY_SALES = "sales_report.daily_sales"
QUERY_ORDER_COUNT = "sales_report.order_count"

#: 집계 대상 주문 상태. 요청값이 아니라 코드가 소유한다 — 이 값을 밖에서 받으면
#: 식별자/리터럴 주입 경로가 열린다(RAW-REP-004).
COUNTED_STATUS = "paid"

_DAILY_SALES_SQL = text(
    """
    SELECT
        DATE(o.ordered_at) AS sales_date,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.ordered_at >= :start_at
      AND o.ordered_at < :end_exclusive
      AND o.status = :status
    GROUP BY DATE(o.ordered_at)
    ORDER BY sales_date ASC
    """
)

_ORDER_COUNT_SQL = text(
    """
    SELECT COUNT(*)
    FROM sales_orders AS o
    WHERE o.ordered_at >= :start_at
      AND o.ordered_at < :end_exclusive
      AND o.status = :status
    """
)


class SalesReportRawRepository(RawRepositoryBase):
    """일별 매출 집계 (Raw SQL)."""

    async def daily_sales(self, *, start_at: date, end_exclusive: date) -> Sequence[RowMapping]:
        """기간 내 일자별 주문 수와 매출 합계.

        Args:
            start_at: 포함 하한.
            end_exclusive: **배타** 상한. 호출자가 계산해 넘긴다.
        """
        return await self.fetch_all(
            _DAILY_SALES_SQL,
            {"start_at": start_at, "end_exclusive": end_exclusive, "status": COUNTED_STATUS},
            query_name=QUERY_DAILY_SALES,
        )

    async def order_count(self, *, start_at: date, end_exclusive: date) -> int:
        """기간 내 집계 대상 주문 수 — scalar 반환 경로의 예시."""
        total = await self.fetch_scalar(
            _ORDER_COUNT_SQL,
            {"start_at": start_at, "end_exclusive": end_exclusive, "status": COUNTED_STATUS},
            query_name=QUERY_ORDER_COUNT,
        )
        return int(total or 0)
