"""매출 리포트 Repository — **Raw SQL 데이터 접근**.

ORM 대응물은 `app/features/catalog/repositories/product_repository.py` 다. 두 파일이
이 프로젝트에서 ORM 과 Raw 가 갈리는 **유일한 지점**이다.

규칙 셋을 지킨다.

1. 외부 값은 전부 named bind parameter (``:start_date``). 문자열 보간 금지 —
   AST 검사가 f-string·``%``·``.format()``·문자열 연결을 실패시킨다.
2. ``query_name`` 은 코드 상수. 요청값으로 만들지 않는다(ADR-018).
3. 결과는 ``RowMapping``. Service 가 Pydantic 으로 검증해서야 밖으로 나간다.

시각 규칙(service-hardening ADR-010):
    ``ordered_at`` 은 UTC 로 저장된다. 기간 경계는 **Service 가 지역 영업일을 UTC 순간으로
    바꾼 값**(``:start_at``·``:end_exclusive``)이고, ``UTCDateTime`` 으로 바인딩해 ORM 과
    같은 형식으로 비교한다. 일자 버킷은 UTC 값을 설정 시간대의 오프셋만큼 옮긴 뒤의
    ``DATE()`` 다 — 그래야 15:30Z(= 다음 날 00:30 KST) 주문이 다음 날로 집계된다.

방언 주의:
    기간 상한은 ``DATE_ADD(:end, INTERVAL 1 DAY)`` 같은 방언 함수 대신 **Service 가 계산한
    배타 상한**을 바인딩한다. 오프셋 이동만은 공통 함수가 없다 — MySQL 은
    ``CONVERT_TZ(col, '+00:00', '+09:00')``, SQLite 는 ``DATE(col, '+540 minutes')`` 다.
    그래서 일별 집계 SQL 만 방언별로 두 개이고, 세션의 방언으로 고른다. 경계·상태
    조건과 alias 는 둘이 같다.

    다만 SQLite 와 MySQL 은 **반환 타입**이 다르다 — ``sales_date`` 가 각각 문자열과
    ``date``, ``gross_amount`` 가 float 과 ``Decimal`` 이다. 그래서 결과를 dict 로
    그냥 흘리지 않고 Pydantic 으로 검증한다. 실제 값 정확성은 MySQL 통합
    테스트가 승인한다(ADR-004).
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import RowMapping, TextClause, bindparam, text

from app.core.models.types import UTCDateTime
from app.core.repositories.raw_repository_base import RawRepositoryBase

#: 로그 라벨. `feature.use_case` 형식의 코드 상수여야 한다(ADR-018).
QUERY_DAILY_SALES = "sales_report.daily_sales"
QUERY_ORDER_COUNT = "sales_report.order_count"

#: 집계 대상 주문 상태. 요청값이 아니라 코드가 소유한다 — 이 값을 밖에서 받으면
#: 식별자/리터럴 주입 경로가 열린다(RAW-REP-004).
COUNTED_STATUS = "paid"

#: 기간 경계는 UTC 순간이다 — 저장 형식(``UTCDateTime``)과 같은 변환을 태운다.
_BOUNDS = (
    bindparam("start_at", type_=UTCDateTime()),
    bindparam("end_exclusive", type_=UTCDateTime()),
)

# ponytail: 오프셋은 조회 시작일 0시의 값 하나로 고정한다(Asia/Seoul 은 DST 가 없어 정확하다).
# DST 가 있는 시간대로 운영하면 전환일 전후 버킷이 한 시간 어긋난다 — 그때는 MySQL 시간대
# 테이블을 적재하고 CONVERT_TZ(o.ordered_at, '+00:00', :tz_name) 처럼 이름으로 바꾼다.
_DAILY_SALES_MYSQL_SQL = text(
    """
    SELECT
        DATE(CONVERT_TZ(o.ordered_at, '+00:00', :tz_offset)) AS sales_date,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.ordered_at >= :start_at
      AND o.ordered_at < :end_exclusive
      AND o.status = :status
    GROUP BY sales_date
    ORDER BY sales_date ASC
    """
).bindparams(*_BOUNDS)

# ponytail: 위와 같은 고정 오프셋 한계(SQLite 는 단위 테스트용 방언이다).
_DAILY_SALES_SQLITE_SQL = text(
    """
    SELECT
        DATE(o.ordered_at, :tz_modifier) AS sales_date,
        COUNT(*) AS order_count,
        COALESCE(SUM(o.total_amount), 0) AS gross_amount
    FROM sales_orders AS o
    WHERE o.ordered_at >= :start_at
      AND o.ordered_at < :end_exclusive
      AND o.status = :status
    GROUP BY sales_date
    ORDER BY sales_date ASC
    """
).bindparams(*_BOUNDS)

_ORDER_COUNT_SQL = text(
    """
    SELECT COUNT(*)
    FROM sales_orders AS o
    WHERE o.ordered_at >= :start_at
      AND o.ordered_at < :end_exclusive
      AND o.status = :status
    """
).bindparams(*_BOUNDS)


def mysql_offset(offset: timedelta) -> str:
    """``timedelta`` → ``CONVERT_TZ`` 의 숫자 오프셋(``+09:00``·``-03:30``)."""
    minutes = int(offset.total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    hours, rest = divmod(abs(minutes), 60)
    return f"{sign}{hours:02d}:{rest:02d}"


class SalesReportRawRepository(RawRepositoryBase):
    """일별 매출 집계 (Raw SQL)."""

    async def daily_sales(
        self, *, start_at: datetime, end_exclusive: datetime, utc_offset: timedelta
    ) -> Sequence[RowMapping]:
        """기간 내 지역 일자별 주문 수와 매출 합계.

        Args:
            start_at: 포함 하한(aware — UTC 로 바인딩된다).
            end_exclusive: **배타** 상한(aware). 호출자가 계산해 넘긴다.
            utc_offset: 일자 버킷을 정할 지역 시간대의 UTC 오프셋.
        """
        statement: TextClause
        params: dict[str, object] = {
            "start_at": start_at,
            "end_exclusive": end_exclusive,
            "status": COUNTED_STATUS,
        }
        if self.session.get_bind().dialect.name == "mysql":
            statement = _DAILY_SALES_MYSQL_SQL
            params["tz_offset"] = mysql_offset(utc_offset)
        else:
            statement = _DAILY_SALES_SQLITE_SQL
            params["tz_modifier"] = f"{int(utc_offset.total_seconds()) // 60:+d} minutes"
        return await self.fetch_all(statement, params, query_name=QUERY_DAILY_SALES)

    async def order_count(self, *, start_at: datetime, end_exclusive: datetime) -> int:
        """기간 내 집계 대상 주문 수 — scalar 반환 경로의 예시."""
        total = await self.fetch_scalar(
            _ORDER_COUNT_SQL,
            {"start_at": start_at, "end_exclusive": end_exclusive, "status": COUNTED_STATUS},
            query_name=QUERY_ORDER_COUNT,
        )
        return int(total or 0)
