"""엔드포인트 테스트용 세션 의존성 오버라이드 — **한 곳**에서만 만든다 (service-hardening C1).

엔드포인트 테스트는 ``get_writer_db_session`` · ``get_read_only_db_session`` 을 in-memory
SQLite 세션으로 바꿔 끼운다. 예전에는 파일마다 같은 픽스처를 손으로 썼고, 두 의존성을
**같은 맨 세션**으로 덮었다. 그러면 운영 의존성이 하는 표시가 빠진다.

* read-only 쪽에 ``mark_read_only`` 가 없으면 GET 핸들러가 몰래 써도 테스트가 통과한다 —
  운영에서는 ``ReadOnlyRoutingError`` 로 500 이 나는 코드가 초록으로 보인다.
* writer 쪽에 ``using_writer`` 가 없으면 운영과 다른 세션 상태로 시험한다.

그래서 운영 의존성(``app/core/db/session.py``)과 **같은 표시**를 붙인 세션을 이 모듈에서만
만든다. 파일마다 오버라이드를 손으로 쓰지 않는 것은 ``tests/test_session_overrides.py`` 가
AST 로 지킨다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import mark_read_only, using_writer
from app.core.db.session import Base, get_read_only_db_session, get_writer_db_session

#: 세션을 yield 하기 직전에 부르는 훅. 커밋 횟수를 세는 테스트가 ``session.commit`` 을
#: 감싸는 데 쓴다 — 표시(using_writer/mark_read_only)는 훅보다 먼저 붙는다.
SessionHook = Callable[[AsyncSession], None]


@asynccontextmanager
async def sqlite_session_overrides(
    app: FastAPI, *, on_session: SessionHook | None = None
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """in-memory SQLite 위에 두 세션 의존성을 오버라이드하고 세션 팩토리를 돌려준다.

    테이블은 ``Base.metadata`` 에 등록된 전부를 만든다 — 호출하는 테스트 파일이 필요한
    모델을 import 해 둔다. 끝나면 ``dependency_overrides`` 를 비우고 엔진을 닫는다.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _writer_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            using_writer(session)
            if on_session is not None:
                on_session(session)
            yield session

    async def _read_only_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            mark_read_only(session)
            if on_session is not None:
                on_session(session)
            yield session

    app.dependency_overrides[get_writer_db_session] = _writer_session
    app.dependency_overrides[get_read_only_db_session] = _read_only_session
    try:
        yield maker
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
