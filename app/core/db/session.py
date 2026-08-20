"""
데이터베이스 세션 및 엔진 관리 모듈

SQLAlchemy 비동기 엔진과 세션 팩토리를 설정합니다.

주요 구성요소:
    - engine: FastAPI 요청 처리용 메인 엔진 = primary(writer) (pool_size=20, max_overflow=20)
    - read_engines: replica(reader) 엔진 목록 (복제 활성 시에만 생성)
    - db_router: 읽기/쓰기 바인딩을 결정하는 DatabaseRouter
    - background_engine: 백그라운드 태스크용 분리 엔진 (pool_size=10, max_overflow=10)
    - AsyncSessionLocal: 메인 세션 팩토리
    - BackgroundSessionLocal: 백그라운드 세션 팩토리
    - get_routed_db_session(): FastAPI DI용 세션 제너레이터 (읽기/쓰기 자동 라우팅)
    - get_read_only_db_session(): 읽기 전용 세션 제너레이터 (쓰기 시도 시 실패)
    - get_writer_db_session(): 쓰기 세션 제너레이터 (항상 primary)
    - get_background_session(): 백그라운드 태스크용 세션 제너레이터

커넥션 풀 분리 이유:
    백그라운드 태스크(예: 접속 로그 저장)가 메인 API 요청의 커넥션 풀을
    고갈시키지 않도록 별도의 풀을 사용합니다.

읽기/쓰기 분리:
    DB_ROUTER_ENABLED=true 면 세션이 구문 성격에 따라 엔진을 자동 선택합니다.
    DB_REPLICATION_ENABLED=true 를 함께 켜면 SELECT 는 replica 로, 쓰기는 primary 로
    나갑니다. 라우터를 끄면 모든 쿼리가 단일 엔진으로 갑니다(기존 동작).
    자세한 규칙은 app/core/db/router.py 를 참고하세요.

사용 예시:
    # FastAPI 엔드포인트에서 (읽기/쓰기 자동 라우팅)
    @app.get("/users")
    async def get_users(session: AsyncSession = Depends(get_routed_db_session)):
        result = await session.execute(select(User))
        return result.scalars().all()

    # 읽기 전용임이 확실한 엔드포인트 (쓰기를 코드 수준에서 차단)
    @app.get("/users/stats")
    async def stats(session: AsyncSession = Depends(get_read_only_db_session)):
        ...

    # 백그라운드 태스크에서
    async def save_log(data: dict):
        async for session in get_background_session():
            session.add(AccessLog(**data))
            await session.commit()
"""

import asyncio
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from sqlalchemy import Table, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.db.router import (
    DatabaseRouter,
    ReadOnlyRoutingError,  # noqa: F401 - re-export
    create_routing_sessionmaker,
    mark_read_only,
    using_writer,
)
from app.core.models.models_base import Base  # noqa: F401 - re-export
from app.utils.logs import get_logger
from config import db_settings

logger = get_logger("database")


# =============================================================================
# 메인 엔진 (FastAPI 요청용) = primary(writer)
# =============================================================================
# API 요청 처리를 위한 커넥션 풀
# 풀 크기는 config 의 DatabaseSettings 가 소유한다 — 배포 형태(worker 수, replica
# 대수)에 따라 달라지고, 총 연결 수가 DB 상한을 넘지 않는지 거기서 검증한다.
# - pool_size: 기본 유지 연결 수
# - max_overflow: 추가 허용 연결 수
# - pool_pre_ping: 연결 사용 전 유효성 검사 (죽은 연결 자동 복구)
# - pool_recycle: 연결 재활용 주기 (MySQL wait_timeout보다 짧게 설정)
engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,  # SQL 로깅 (개발 시 True로 설정)
    pool_size=db_settings.DB_POOL_SIZE,
    max_overflow=db_settings.DB_MAX_OVERFLOW,
    pool_timeout=db_settings.DB_POOL_TIMEOUT,
    pool_recycle=db_settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",  # 반환 시 롤백으로 세션 초기화
    connect_args={
        "connect_timeout": 10,  # DB 연결 타임아웃 (초)
        "charset": "utf8mb4",  # 이모지 등 4바이트 UTF-8 지원
    },
)

# `engine` 은 SQLAdmin·Alembic 등 기존 소비처가 쓰는 이름이라 유지하고,
# 역할이 드러나는 별칭을 함께 노출한다.
writer_engine = engine


# =============================================================================
# replica 엔진 (읽기 전용) — 복제 활성 시에만 생성
# =============================================================================
def _create_read_engine(url: str) -> AsyncEngine:
    """replica 용 엔진을 만든다.

    읽기는 보통 쓰기보다 트래픽이 많고 트랜잭션이 짧으므로 풀을 primary 와
    같은 크기로 잡되, replica 대수만큼 커넥션이 곱해진다는 점에 유의한다.
    """
    return create_async_engine(
        url=url,
        echo=False,
        pool_size=db_settings.DB_POOL_SIZE,
        max_overflow=db_settings.DB_MAX_OVERFLOW,
        pool_timeout=db_settings.DB_POOL_TIMEOUT,
        pool_recycle=db_settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        pool_reset_on_return="rollback",
        connect_args={
            "connect_timeout": 10,
            "charset": "utf8mb4",
        },
    )


# 복제가 꺼져 있으면 빈 목록 → 라우터는 읽기도 primary 로 보낸다.
read_engines: list[AsyncEngine] = [
    _create_read_engine(url) for url in db_settings.MYSQL_REPLICA_URLS
]

# 읽기/쓰기 바인딩을 결정하는 라우터 (라우터가 꺼져 있어도 헬스체크용으로 구성해 둔다)
db_router = DatabaseRouter(
    writer=engine,
    readers=read_engines,
    sticky_after_write=db_settings.DB_READ_STICKY_AFTER_WRITE,
)


# =============================================================================
# 메인 세션 팩토리 (FastAPI DI용)
# =============================================================================
# - expire_on_commit=False: 커밋 후에도 객체 속성 접근 가능
# - autoflush=False: 명시적 flush 권장 (예측 가능한 쿼리 타이밍)
#
# 라우터가 켜져 있으면 RoutingSession 이 구문마다 엔진을 고르고,
# 꺼져 있으면 단일 엔진에 직접 바인딩한다(오버헤드·동작 모두 기존 그대로).
if db_settings.DB_ROUTER_ENABLED:
    AsyncSessionLocal = create_routing_sessionmaker(db_router)
else:
    AsyncSessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

# 기동 시 라우팅 구성을 한 줄로 남긴다 (비밀번호는 config.mask_dsn 이 마스킹).
logger.info("[database] 라우팅 구성: %s", db_settings.describe_routing())


# =============================================================================
# 백그라운드 태스크 전용 엔진 (메인 풀과 분리)
# =============================================================================
# 백그라운드 작업(로그 저장, 비동기 처리 등)용 별도 커넥션 풀
# 메인 API 요청과 분리하여 풀 고갈 방지
#
# 백그라운드 작업은 대부분 쓰기(접속 로그 적재 등)이므로 primary 에 직접 붙인다.
# 라우팅을 태우지 않는 편이 예측 가능하고, replica 로 새는 사고도 없다.
background_engine = create_async_engine(
    url=db_settings.MYSQL_WRITER_URL,
    echo=False,
    pool_size=db_settings.DB_BACKGROUND_POOL_SIZE,
    max_overflow=db_settings.DB_BACKGROUND_MAX_OVERFLOW,
    pool_timeout=db_settings.DB_BACKGROUND_POOL_TIMEOUT,
    pool_recycle=db_settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    pool_reset_on_return="rollback",
    connect_args={
        "connect_timeout": 10,
        "charset": "utf8mb4",
    },
)

# 백그라운드 세션 팩토리
BackgroundSessionLocal = async_sessionmaker(
    bind=background_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


@asynccontextmanager
async def background_session() -> AsyncGenerator[AsyncSession, None]:
    """요청 밖(백그라운드 태스크·Celery)에서 사용하는 세션 컨텍스트.

    요청 스코프 DI(get_routed_db_session)를 쓸 수 없는 곳에서 트랜잭션 경계를 제공한다.
    예외 시 롤백하고, 컨텍스트 종료 시 세션을 닫는다. 커밋은 호출자가 명시한다.

    Example:
        async with background_session() as session:
            await SomeService(session).do_write()
            await session.commit()
    """
    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def owned_tables() -> list[Table]:
    """App Registry 가 소유한 모델의 테이블만 돌려준다.

    ``Base.metadata`` 는 전역이라, 한 번이라도 import 된 모델은 registry 에 없어도
    거기 남는다 — 테스트가 정의한 임시 모델까지 섞인다. 그 전체를 create_all 에
    넘기면 **설치하지 않은 앱의 테이블이 개발 DB 에 생긴다**. 그래서 registry 가
    실제로 소유한 것만 골라 ``tables=`` 로 명시한다 (C-3).
    """
    from app.core.apps import apps

    # registry 는 매핑 클래스를 ``type`` 으로 돌려준다(프레임워크 중립). 여기서
    # 우리 Base 하위임을 아는 지점이므로 좁혀 쓴다.
    models = cast(list[type[Base]], apps.get_models())
    return [cast(Table, model.__table__) for model in models]


async def create_db_tables(*, populate: bool = True) -> int:
    """등록 앱이 소유한 테이블을 생성한다.

    Args:
        populate: registry 를 여기서 채울지 여부. 조립부(resources)가 이미 채웠으면
            ``False`` 로 넘긴다 — 같은 startup 에서 discovery 가 두 번 돌면 로그와
            소요 시간이 어긋난다.

    Returns:
        생성 대상 테이블 수. 0이면 **DB 에 접속하지 않는다**.

    Note:
        모델 수집 대상은 ``config.INSTALLED_APPS`` 다. 디렉터리를 훑지 않는다 —
        등록하지 않은 앱의 테이블이 개발 DB 에만 생겨 운영과 어긋나는 일을 막는다.
    """
    if populate:
        from app.core.apps import apps
        from config import INSTALLED_APPS

        # ready() 는 실행하지 않는다 — 테이블 생성은 앱 결선을 필요로 하지 않는다.
        apps.populate(INSTALLED_APPS, run_ready=False)

    tables = owned_tables()
    logger.info("[database] 모델 등록: %d개 %s", len(tables), [t.name for t in tables])

    if not tables:
        # 모델이 하나도 없으면 만들 것이 없다. 여기서 접속하면 "테이블 0개를
        # 만들려고 DB 가 떠 있어야 하는" 이상한 의존이 생긴다.
        logger.info("[database] 소유 테이블이 없어 DB 접속과 테이블 생성을 건너뛴다")
        return 0

    logger.info("Creating database tables...")

    async with asyncio.timeout(30):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all, tables=tables)

    return len(tables)


async def get_routed_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 의존성 주입용 세션 제너레이터

    FastAPI 엔드포인트에서 Depends()로 사용합니다.
    요청 종료 시 자동으로 세션이 닫힙니다.
    예외 발생 시 자동 롤백됩니다.

    Yields:
        AsyncSession: 데이터베이스 세션

    Example:
        @app.get("/users/{id}")
        async def get_user(
            id: str,
            session: AsyncSession = Depends(get_routed_db_session)
        ):
            user = await session.get(User, id)
            return user

    Note:
        - 세션은 요청 범위(request scope)로 관리됩니다
        - 한 요청 내에서 여러 번 호출해도 같은 세션을 반환하지 않습니다
        - 트랜잭션 경계는 쓰기 핸들러 본문이 `await service.commit()` 으로 관리합니다
    """
    start_time = time.perf_counter()

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            # 예외 **메시지**는 남기지 않는다 — DB 예외의 str() 에는 실행된 SQL 과
            # 바인딩된 값이 들어 있고, 이 로거 이름(app.core.*)은 sql_noise 필터를
            # 통과한다(C-5). 타입과 소요시간만으로 어디서 굴렀는지는 충분히 좁혀진다.
            logger.error(
                "[get_routed_db_session] ROLLBACK - error: %s, duration: %.1fms",
                type(e).__name__,
                (time.perf_counter() - start_time) * 1000,
            )
            raise e


async def get_read_only_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    읽기 전용 세션 제너레이터 (FastAPI DI)

    조회만 하는 엔드포인트에서 사용합니다. 라우터가 켜져 있으면 세션이
    replica 에 고정되고, 쓰기를 시도하면 ``ReadOnlyRoutingError`` 로 즉시 실패해
    "읽기 전용 핸들러가 몰래 쓰는" 사고를 코드 수준에서 차단합니다.

    Yields:
        AsyncSession: 읽기 전용 데이터베이스 세션

    Example:
        @app.get("/posts")
        async def list_posts(session: AsyncSession = Depends(get_read_only_db_session)):
            result = await session.execute(select(Post))
            return result.scalars().all()

    Note:
        - DB_ROUTER_ENABLED=false 면 라우팅·쓰기 차단이 동작하지 않고
          get_routed_db_session() 과 동일하게 단일 엔진 세션을 반환합니다.
        - 복제 지연을 허용할 수 없는 읽기라면 get_routed_db_session() + using_writer() 를 쓰세요.
    """
    async with AsyncSessionLocal() as session:
        mark_read_only(session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_writer_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    쓰기 세션 제너레이터 (FastAPI DI)

    항상 primary 로 나가는 세션을 반환합니다. 쓰기 직후 같은 요청에서 조회까지
    해야 하는 핸들러(예: 생성 후 결과 반환)에 적합합니다.

    Yields:
        AsyncSession: primary 에 고정된 데이터베이스 세션

    Note:
        get_routed_db_session() 도 쓰기를 감지하면 primary 로 전환되므로 대부분의 경우
        구분 없이 써도 됩니다. 이 의존성은 "이 핸들러는 쓰기다"를 명시하고,
        첫 SELECT 조차 replica 로 새지 않도록 보장할 때 사용합니다.
    """
    async with AsyncSessionLocal() as session:
        using_writer(session)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_background_session() -> AsyncGenerator[AsyncSession, None]:
    """
    백그라운드 태스크용 세션 제너레이터

    메인 커넥션 풀과 분리된 백그라운드 풀을 사용합니다.
    asyncio.create_task() 등으로 생성된 백그라운드 작업에서 사용합니다.

    Yields:
        AsyncSession: 백그라운드 작업용 데이터베이스 세션

    Example:
        async def save_access_log(data: dict):
            async for session in get_background_session():
                log = UserAccessLog(**data)
                session.add(log)
                await session.commit()

    Note:
        - 메인 API 풀과 분리되어 있어 백그라운드 작업이 API를 블로킹하지 않습니다
        - 요청 밖 트랜잭션 경계는 background_session() 컨텍스트 사용을 권장합니다
    """
    start_time = time.perf_counter()

    async with BackgroundSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(
                f"[get_background_session] ROLLBACK - "
                f"error: {type(e).__name__}: {e}, "
                f"duration: {(time.perf_counter() - start_time)*1000:.1f}ms"
            )
            raise e


# readiness 검사 예산. 넘기면 준비되지 않은 것으로 본다 — 오케스트레이터를
# 기다리게 하는 것보다 503 을 빨리 돌려주는 편이 낫다.
READINESS_TIMEOUT_SECONDS = 2.0


async def ping_writer_db(timeout: float = READINESS_TIMEOUT_SECONDS) -> None:
    """writer DB 에 ``SELECT 1`` 을 실행한다 (readiness 용).

    replica 가 아니라 **writer** 를 보는 이유는, 쓰기가 불가능한 인스턴스로
    트래픽이 들어오는 것이 준비 실패의 실질적 의미이기 때문이다.

    Raises:
        TimeoutError: ``timeout`` 안에 응답하지 못한 경우.
        Exception: 연결·쿼리 실패 시 드라이버 예외를 그대로 올린다. 호출자가
            사용자 응답에 내용을 싣지 않도록 주의해야 한다(DSN·자격증명 노출).
    """
    async with asyncio.timeout(timeout):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))


async def dispose_engine() -> None:
    """
    앱 종료 시 엔진 리소스 정리

    lifespan의 shutdown 단계에서 호출됩니다.
    모든 커넥션 풀을 정리하고 데이터베이스 연결을 종료합니다.

    Note:
        이 함수가 호출되지 않으면 커넥션이 정리되지 않아
        데이터베이스에 좀비 연결이 남을 수 있습니다.
    """
    logger.info("[dispose_engine] Disposing database engines...")
    await engine.dispose()
    logger.info("[dispose_engine] Main engine disposed")

    # replica 엔진도 함께 정리한다 (복제 비활성이면 빈 목록이라 no-op).
    for index, read_engine in enumerate(read_engines):
        await read_engine.dispose()
        logger.info("[dispose_engine] Read replica engine #%d disposed", index)

    await background_engine.dispose()
    logger.info("[dispose_engine] Background engine disposed - ALL DONE")
