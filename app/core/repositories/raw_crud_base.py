"""Raw SQL 실행 primitive (requirements RAW-REP-001).

ORM Base 와 **상속으로 이어지지 않는** 별도 계층이다(AR-003). 하나의 Base 가 ORM 모델과
Raw row 를 함께 돌려주면 호출부가 무엇을 받았는지 타입으로 알 수 없다.

여기서 하는 일은 셋뿐이다.

1. ``TextClause`` 를 실행하고 결과를 ``RowMapping`` / scalar / rowcount 로 돌려준다.
2. 구문에 **읽기/쓰기 의도**를 붙인다 — 라우터가 SQL 문자열을 해석하지 않아도 되도록.
3. 쓰기를 읽기 전용 세션에서 **실행 전에** 거부한다.

commit·rollback 은 하지 않는다. 트랜잭션 경계는 View 가 소유한다(ORM 경로와 같다).

왜 문자열이 아니라 ``TextClause`` 인가:
    문자열을 받으면 이 계층이 "안전한 문자열"과 "포맷된 문자열"을 구분할 수 없다.
    ``text()`` 를 호출부가 직접 부르게 하면 정적 검사가 그 호출만 보면 된다.

.. note::
   ``UpdatedAtMixin.onupdate`` 는 ORM 이 UPDATE 를 낼 때만 동작한다. Raw UPDATE 는
   ``updated_at`` 을 갱신하지 않으므로 SQL 에 직접 써야 한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import RowMapping, TextClause
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.router import (
    ReadOnlyRoutingError,
    is_read_only_session,
    read_intent,
    write_intent,
)

#: bind parameter 묶음. executemany(딕셔너리 리스트)는 지원하지 않는다 — 필요해지면
#: 그때 계약을 넓힌다.
Params = Mapping[str, Any] | None


class RawCRUDBase:
    """Raw SQL 실행 primitive. 하위 계층이며 직접 상속하지 않는다.

    기능 Repository 는 :class:`~app.core.repositories.raw_repository_base.RawRepositoryBase`
    를 상속한다. 이 클래스의 메서드가 protected 인 이유는 ``query_name`` 검증과 로깅을
    건너뛴 경로를 남기지 않기 위해서다.

    Attributes:
        session: 비동기 데이터베이스 세션.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _intent(self, statement: TextClause, *, write: bool) -> TextClause:
        """구문에 의도를 붙이고, 쓰기면 읽기 전용 세션에서 실행 전에 막는다.

        라우터에도 같은 차단이 있지만 그쪽은 ``DB_ROUTER_ENABLED=false`` 면 통째로
        꺼진다. 읽기 전용 표식은 라우터와 무관하게 붙으므로 여기서 한 번 더 본다 —
        "설정을 끄면 보안도 꺼지는" 상태를 만들지 않는다.
        """
        if not write:
            return read_intent(statement)
        if is_read_only_session(self.session):
            raise ReadOnlyRoutingError(
                "읽기 전용 세션에서 Raw 쓰기를 시도했습니다. "
                "쓰기에는 get_writer_db_session() 을 사용하세요."
            )
        return write_intent(statement)

    async def _fetch_one(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        for_update: bool = False,
    ) -> RowMapping | None:
        """첫 행을 ``RowMapping`` 으로. 결과가 없으면 ``None``.

        Args:
            statement: ``text()`` 로 만든 구문.
            params: named bind parameter.
            for_update: ``SELECT ... FOR UPDATE`` 처럼 잠금을 잡는 읽기면 True.
                쓰기로 취급해 writer 에 고정한다 — replica 에서 잠근 행은 아무것도
                보호하지 않는다.
        """
        result = await self.session.execute(self._intent(statement, write=for_update), params)
        return result.mappings().first()

    async def _fetch_all(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        for_update: bool = False,
    ) -> Sequence[RowMapping]:
        """모든 행을 ``RowMapping`` 목록으로. 결과가 없으면 빈 목록."""
        result = await self.session.execute(self._intent(statement, write=for_update), params)
        return result.mappings().all()

    async def _fetch_scalar(
        self,
        statement: TextClause,
        params: Params = None,
        *,
        for_update: bool = False,
    ) -> Any:
        """첫 행 첫 컬럼. 결과가 없으면 ``None`` (COUNT 등 집계용)."""
        result = await self.session.execute(self._intent(statement, write=for_update), params)
        return result.scalar()

    async def _execute(self, statement: TextClause, params: Params = None) -> int:
        """INSERT/UPDATE/DELETE 를 실행하고 영향 행 수를 돌려준다.

        commit 하지 않는다. rowcount 의 의미는 드라이버 설정에 좌우되므로
        (MySQL ``CLIENT_FOUND_ROWS``) 이 값으로 **존재 여부를 판단하지 않는다** —
        그 판단은 조회로 한다.
        """
        result = await self.session.execute(self._intent(statement, write=True), params)
        return int(getattr(result, "rowcount", -1))
