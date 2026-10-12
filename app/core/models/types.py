"""DB 시각 타입 — UTC·마이크로초 저장 (service-hardening ADR-010 · C-9).

``DateTime(timezone=True)`` 는 MySQL 에서 아무 일도 하지 않는다 — ``DATETIME`` 은 tz 를
저장하지 않고, 드라이버는 aware 값의 tzinfo 를 떼어 **벽시계만** 보낸다. 그래서 KST 로 쓴
값과 UTC 로 쓴 값이 같은 컬럼에 구분 없이 섞이고, fsp 가 0 이라 마이크로초도 잘린다.

:class:`UTCDateTime` 이 저장 경계에서 그것을 막는다.

* bind: aware 값을 UTC 로 바꾼 뒤 tzinfo 를 뗀다. **naive 값은 ``ValueError``** — 어느
  시간대의 벽시계인지 모르는 값을 조용히 저장하면 그 오해는 나중에 데이터로 돌아온다.
* result: DB 의 naive 값에 ``tzinfo=UTC`` 를 붙인다. 응답은 오프셋(``Z``)을 갖는다.
* MySQL 은 ``DATETIME(6)``(마이크로초), 그 밖의 방언은 ``DateTime()``.

Raw SQL(``text()``)의 bind 값은 컬럼 타입을 모른다. 시각을 바인딩할 때는
``bindparam(name, type_=UTCDateTime())`` 로 같은 변환을 태운다.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime
from sqlalchemy.dialects import mysql
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine


class UTCDateTime(TypeDecorator[datetime]):
    """aware datetime 만 받아 UTC naive 로 저장하고, 읽을 때 UTC 를 붙인다."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mysql":
            return dialect.type_descriptor(mysql.DATETIME(fsp=6))
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(
                "naive datetime 은 저장할 수 없습니다 — 시간대를 알 수 없습니다. "
                "timezone_settings.utc_now() 또는 aware datetime 을 쓰세요."
            )
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


def render_item(type_: str, obj: Any, autogen_context: Any) -> str | bool:
    """Alembic autogenerate 렌더 훅 — ``UTCDateTime`` 을 SQLAlchemy 표준 타입으로 적는다.

    그대로 두면 migration 파일에 ``app.core.models.types.UTCDateTime()`` 이 import 없이
    찍힌다. migration 은 앱 코드를 import 하지 않는다(나중에 이 모듈이 바뀌어도 과거
    revision 이 그대로 돌아야 한다). 그래서 DB 에 실제로 만들어지는 모양을 적는다.
    """
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return "sa.DateTime().with_variant(mysql.DATETIME(fsp=6), 'mysql')"
    return False
