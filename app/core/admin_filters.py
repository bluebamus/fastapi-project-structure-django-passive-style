"""관리 목록의 날짜 필터 — 지역 날짜를 UTC 범위로 바꿔 ``UTCDateTime`` 컬럼을 거른다.

sqladmin 0.32 의 ``OperationColumnFilter`` 는 ``UTCDateTime``(TypeDecorator)을 날짜형으로 알아보지
못해 입력 문자열을 그대로 바인딩하고, ``UTCDateTime`` 이 그것을 거부해 목록이 500 이 된다
(admin-login ADR-009). 이 클래스는 같은 필터 프로토콜(``has_operator``·``template``·
``parameter_name``·``get_operation_options_for_model``·``get_filtered_query``)을 따르되, 값을
``TIME_ZONE`` 의 날짜로 읽어 지역 0시를 aware UTC 순간으로 바꾼 뒤 범위 조건으로 질의한다
(security-ops-hardening ADR-005).

sqladmin 을 import 하지 않는다 — 프로토콜은 이름으로 맞춘다. 그래서 ``ADMIN_DISABLED=true`` 에서
이 모듈이 로드돼도 sqladmin 이 딸려오지 않는다(SEC-01). 쓰는 곳은 각 앱의 ``admin.py`` 다.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import Select

from app.utils.logs import get_logger
from config import TimezoneSettings, timezone_settings

logger = get_logger("app.core.admin_filters")

#: 입력 형식 — ``<input type="date">`` 가 보내는 값과 같다.
DATE_FORMAT = "%Y-%m-%d"


class LocalDateFilter:
    """``created_at`` 같은 UTC 시각 컬럼을 지역 날짜로 거르는 sqladmin 필터.

    연산(``<parameter>_op``):
        * ``on``     — 그 날 하루 ``[D 0시, D+1 0시)``
        * ``from``   — 그 날 이후, 그 날 포함 ``>= D 0시``
        * ``before`` — 그 날 이전, 그 날 제외 ``< D 0시``

    형식이 틀린 값이나 모르는 연산은 **필터를 적용하지 않고** 목록을 그대로 보여 준다(WARNING 로그) —
    잘못 친 날짜 하나로 관리 화면이 500 이 되지 않는다.
    """

    has_operator = True
    template = "sqladmin/filters/local_date_filter.html"
    OPERATIONS: tuple[tuple[str, str], ...] = (
        ("on", "같은 날"),
        ("from", "이후(포함)"),
        ("before", "이전(미포함)"),
    )

    def __init__(
        self,
        column: Any,
        title: str = "생성일",
        parameter_name: str | None = None,
        timezone: TimezoneSettings = timezone_settings,
    ) -> None:
        self.column = column
        self.title = title
        self.parameter_name = parameter_name or column.key
        self.timezone = timezone

    def get_operation_options_for_model(self, model: Any) -> list[tuple[str, str]]:
        return list(self.OPERATIONS)

    async def lookups(
        self, request: Any, model: Any, run_query: Callable[[Select[Any]], Any]
    ) -> list[tuple[str, str]]:
        return []  # 연산 필터는 lookups 를 쓰지 않는다(sqladmin 이 연산 목록으로 그린다).

    def quick_ranges(self) -> list[tuple[str, str, str]]:
        """빠른 선택 — (표시 이름, 연산, 지역 날짜). 오늘·최근 7일·최근 30일(오늘 포함)."""
        today = self.today()
        return [
            ("오늘", "on", today.isoformat()),
            ("최근 7일", "from", (today - timedelta(days=6)).isoformat()),
            ("최근 30일", "from", (today - timedelta(days=29)).isoformat()),
        ]

    def today(self) -> date:
        """``TIME_ZONE`` 기준 오늘."""
        return self.timezone.utc_now().astimezone(self.timezone.tz).date()

    async def get_filtered_query(
        self, query: Select[Any], operation: str, value: Any, model: Any
    ) -> Select[Any]:
        try:
            day = datetime.strptime(str(value).strip(), DATE_FORMAT).date()
        except ValueError:
            logger.warning("[admin] 날짜 필터 값 무시 parameter=%s", self.parameter_name)
            return query
        start = self.timezone.local_midnight_utc(day)
        if operation == "on":
            end = self.timezone.local_midnight_utc(day + timedelta(days=1))
            return query.where(self.column >= start, self.column < end)
        if operation == "from":
            return query.where(self.column >= start)
        if operation == "before":
            return query.where(self.column < start)
        logger.warning("[admin] 날짜 필터 연산 무시 parameter=%s", self.parameter_name)
        return query
