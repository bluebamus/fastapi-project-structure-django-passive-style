"""
Database 모듈

데이터베이스 연결과 세션 관리를 제공합니다.
요청 스코프 세션은 get_read_only_db_session(조회) / get_writer_db_session(쓰기) Dependency,
요청 밖 작업은 background_session(컨텍스트)을 사용한다. get_routed_db_session 은 의도를
미리 정할 수 없는 예외 경로용이다.
(별도 UnitOfWork 는 없다. 커밋은 요청이면 쓰기 핸들러 본문, 요청 밖이면 background_session 호출자가 한다.)

읽기/쓰기 분리는 DatabaseRouter 가 담당한다(app/core/db/router.py).
.env 의 DB_ROUTER_ENABLED / DB_REPLICATION_ENABLED 로 활성화한다.
"""

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.db.session import (
    READINESS_TIMEOUT_SECONDS,
    AsyncSessionLocal,
    BackgroundSessionLocal,
    Base,
    background_engine,
    background_session,
    create_db_tables,
    db_router,
    dispose_engine,
    engine,
    get_background_session,
    get_read_only_db_session,
    get_routed_db_session,
    get_writer_db_session,
    ping_writer_db,
    read_engines,
    writer_engine,
)

__all__ = [
    "Base",
    "engine",
    "writer_engine",
    "read_engines",
    "background_engine",
    "db_router",
    "DatabaseRouter",
    "ReadOnlyRoutingError",
    "create_routing_sessionmaker",
    "using_writer",
    "mark_read_only",
    "AsyncSessionLocal",
    "BackgroundSessionLocal",
    # 정식 이름 (ADR-009)
    "get_routed_db_session",
    "get_read_only_db_session",
    "get_writer_db_session",
    "get_background_session",
    "ping_writer_db",
    "READINESS_TIMEOUT_SECONDS",
    "background_session",
    "create_db_tables",
    "dispose_engine",
]
