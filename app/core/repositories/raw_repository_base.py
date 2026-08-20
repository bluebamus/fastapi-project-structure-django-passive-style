"""Raw SQL Repository 의 공개 계약 (requirements RAW-REP-002).

기능 Raw Repository 가 상속하는 클래스다. primitive 에 세 가지를 얹는다.

* **query_name 검증** — 로그에 남는 유일한 식별자다. 사용자 입력에서 만들면 로그
  cardinality 가 터지고 값이 그대로 새어 나간다. 그래서 형식과 길이를 실행 전에 본다.
* **구조화 로그** — ``query_name`` · 소요 시간 · 성공/실패만 남긴다. SQL 본문과 params 는
  남기지 않는다. 값이 거기 있다.
* **예외 변환** — 드라이버 원문을 끊고(:func:`~app.core.db.errors.convert_db_error`)
  안전한 애플리케이션 예외로 바꾼다.

도메인 SQL 은 여기 두지 않는다. Base 가 ``daily_sales`` 를 알기 시작하면 다음 리포트도
여기로 오고, 결국 모든 기능이 Base 를 통해 서로 결합된다.

사용법::

    class SalesReportRawRepository(RawRepositoryBase):
        async def daily_sales(self, *, start_date, end_date):
            statement = text("SELECT ... WHERE d >= :start_date")
            return await self.fetch_all(
                statement,
                {"start_date": start_date},
                query_name="sales_report.daily_sales",
            )
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

from sqlalchemy import RowMapping, TextClause
from sqlalchemy.exc import SQLAlchemyError

from app.core.db.errors import convert_db_error
from app.core.repositories.raw_crud_base import Params, RawCRUDBase
from app.utils.logs import get_logger

logger = get_logger("repository.raw")

#: ``feature.use_case`` 형식. 소문자·숫자·밑줄만, 점 하나로 두 마디.
#: 좁게 잡은 이유는 이 값이 로그 라벨이 되기 때문이다 — 자유 문자열이면 관측 도구에서
#: 시계열이 무한히 늘어나고, 사용자 입력이 섞였을 때 그걸 알아볼 방법이 없다.
#:
#: ``$`` 가 아니라 ``\Z`` 를 쓴다. ``$`` 는 끝의 개행 **앞**에서도 맞는다 —
#: 개행이 붙은 query_name 이 통과하면 그 개행이 로그 한 줄을 둘로 쪼갠다.
QUERY_NAME_PATTERN = re.compile(r"\A[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\Z")

#: 로그 라벨 길이 상한. 형식이 맞아도 긴 값은 거부한다.
QUERY_NAME_MAX_LENGTH = 64


class InvalidQueryNameError(ValueError):
    """``query_name`` 이 형식·길이 규칙을 벗어났을 때. 실행 **전에** 발생한다."""


def validate_query_name(query_name: str) -> str:
    """``query_name`` 을 검증하고 그대로 돌려준다.

    Raises:
        InvalidQueryNameError: 타입·길이·형식 중 하나라도 어긋난 경우.
    """
    if not isinstance(query_name, str):
        raise InvalidQueryNameError(
            f"query_name 은 문자열이어야 합니다: {type(query_name).__name__}"
        )
    if len(query_name) > QUERY_NAME_MAX_LENGTH:
        raise InvalidQueryNameError(
            f"query_name 이 {QUERY_NAME_MAX_LENGTH}자를 넘습니다 (길이 {len(query_name)})."
        )
    if not QUERY_NAME_PATTERN.match(query_name):
        raise InvalidQueryNameError(
            "query_name 은 'feature.use_case' 형식의 코드 상수여야 합니다 "
            f"(받은 값의 형식이 규칙에 맞지 않습니다, 길이 {len(query_name)})."
        )
    return query_name


class RawRepositoryBase(RawCRUDBase):
    """Raw SQL Repository 의 공개 계약.

    ORM 쪽 ``BaseRepository`` 와 **상속 관계가 없다**(AR-003). 대응은 이렇다.

    ==========================  ==============================
    ORM                         Raw
    ==========================  ==============================
    ``get_one`` / ``get_by_id``  ``fetch_one``
    ``get_all``                  ``fetch_all``
    ``count`` / ``exists``       ``fetch_scalar``
    ``create``/``update``/``delete``  ``execute``
    ==========================  ==============================

    Attributes:
        session: 비동기 데이터베이스 세션.
    """

    @contextmanager
    def _observed(self, query_name: str, *, write: bool) -> Iterator[None]:
        """실행을 감싸 소요 시간과 성공/실패를 남기고, DB 예외를 안전하게 바꾼다.

        남기는 것은 ``query_name`` · 경과 시간 · 성공 여부뿐이다. SQL 본문과 bind 값은
        의도적으로 제외한다 — 로그는 지워지지 않고, 값은 대개 개인정보다.
        """
        validate_query_name(query_name)
        operation = "RAW_WRITE" if write else "RAW_READ"
        started = time.perf_counter()
        try:
            yield
        except SQLAlchemyError as exc:
            logger.error(
                "[%s] %s failed in %.1fms",
                operation,
                query_name,
                (time.perf_counter() - started) * 1000,
            )
            raise convert_db_error(
                exc,
                operation=operation,
                model=type(self).__name__,
                query=query_name,
            ) from None
        else:
            logger.debug(
                "[%s] %s ok in %.1fms",
                operation,
                query_name,
                (time.perf_counter() - started) * 1000,
            )

    async def fetch_one(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        query_name: str,
        for_update: bool = False,
    ) -> RowMapping | None:
        """첫 행을 ``RowMapping`` 으로. 없으면 ``None``.

        Args:
            statement: ``text()`` 구문. 외부 값은 전부 named bind parameter 로.
            params: bind parameter.
            query_name: ``feature.use_case`` 형식의 **코드 상수**. 요청값 금지.
            for_update: 잠금 읽기면 True — writer 로 고정된다.

        Raises:
            InvalidQueryNameError: ``query_name`` 이 규칙을 벗어난 경우.
            ReadOnlyRoutingError: 잠금 읽기를 읽기 전용 세션에서 시도한 경우.
        """
        with self._observed(query_name, write=for_update):
            return await self._fetch_one(statement, params, for_update=for_update)

    async def fetch_all(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        query_name: str,
        for_update: bool = False,
    ) -> Sequence[RowMapping]:
        """모든 행을 ``RowMapping`` 목록으로. 없으면 빈 목록."""
        with self._observed(query_name, write=for_update):
            return await self._fetch_all(statement, params, for_update=for_update)

    async def fetch_scalar(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        query_name: str,
        for_update: bool = False,
    ) -> Any:
        """첫 행 첫 컬럼. 없으면 ``None``."""
        with self._observed(query_name, write=for_update):
            return await self._fetch_scalar(statement, params, for_update=for_update)

    async def execute(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        query_name: str,
    ) -> int:
        """INSERT/UPDATE/DELETE 를 실행하고 영향 행 수를 돌려준다.

        commit 하지 않는다 — 트랜잭션 경계는 View 가 소유한다.

        Raises:
            ReadOnlyRoutingError: 읽기 전용 세션에서 호출한 경우(실행 전에 거부).
        """
        with self._observed(query_name, write=True):
            return await self._execute(statement, params)
