"""애플리케이션 조립 — ``create_app()`` factory.

``main.py`` 가 모듈 최상단에서 앱을 조립하던 구조를 factory 로 옮겼다. 이유는 하나다:
**테스트가 격리된 앱을 만들 수 있어야 한다.** 모듈 최상단 조립은 프로세스당 하나뿐이라
"auth 를 뺀 앱", "ADMIN=False 인 앱", "다른 registry 를 쓴 앱" 을 만들 수 없고, 그러면
수동 등록의 핵심 계약(등록 안 한 앱은 안 붙는다)을 실행으로 증명할 방법이 없다.

조립 순서(§6.5)는 다음과 같고, 순서 자체가 계약이다.

1. 설치 앱 목록 결정 (``config.INSTALLED_APPS`` 또는 주입값)
2. registry population — config → models → ``ready()``
3. FastAPI 생성 + lifespan 연결
4. CORS · user-info middleware · 예외 핸들러
5. registry 기반 Router 설치
6. health · Scalar docs
7. 허용된 경우에만 registry 기반 SQLAdmin 설치

2번이 3번보다 먼저인 이유는 startup 테이블 생성과 migration metadata 가 같은 모델
집합을 봐야 하기 때문이다. 7번이 마지막인 이유는 SEC-01 — ``ADMIN=False`` 면 sqladmin
이 아예 import 되지 않아야 한다.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from scalar_fastapi import get_scalar_api_reference
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.apps import Apps
from app.core.apps import apps as default_registry
from app.core.apps.wiring import create_admin, install_routers
from app.core.db.errors import driver_error_code
from app.core.db.session import READINESS_TIMEOUT_SECONDS, engine, ping_writer_db
from app.core.exception import AppException, ErrorResponse, ValidationException
from app.core.middlewares.cors_middleware import CustomCORSMiddleware
from app.core.middlewares.user_info_middleware import setup_user_info_middleware
from app.core.resources import manage_application_resources
from app.core.tags_metadata import tags_metadata
from app.utils.logs import get_logger
from config import INSTALLED_APPS, app_settings

logger = get_logger("app.core.bootstrap")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """애플리케이션 수명 주기 — 자원 관리는 ``manage_application_resources`` 가 한다.

    여기에는 조립만 남긴다. startup 중간에 실패했을 때의 해제 경로와 종료 순서가
    자원 관리자 한 곳에 모여 있어야, "정상 종료에서는 닫는데 실패 경로에서는
    새는" 상태가 생기지 않는다(development-plan §9.4·§9.5).
    """
    async with manage_application_resources(app):
        yield


def _register_exception_handlers(app: FastAPI) -> None:
    """4가지 글로벌 예외 핸들러를 등록합니다."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """
        애플리케이션 커스텀 예외 핸들러

        AppException 및 하위 예외들을 처리하여 일관된 에러 응답을 반환합니다.
        """
        logger.error(
            "[AppException] %s: %s",
            exc.error_code,
            exc.message,
            extra={
                "path": request.url.path,
                "method": request.method,
                "error_code": exc.error_code,
                "detail": exc.detail,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        요청 유효성 검증 예외 핸들러

        Pydantic 유효성 검증 실패 시 일관된 에러 응답을 반환합니다.
        """
        errors = exc.errors()
        detail = [
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
            for error in errors
        ]
        logger.warning(
            "[ValidationError] 요청 유효성 검증 실패",
            extra={
                "path": request.url.path,
                "method": request.method,
                "errors": detail,
            },
        )
        validation_exc = ValidationException(
            message="요청 데이터 유효성 검증에 실패했습니다.",
            detail=detail,
        )
        return JSONResponse(
            status_code=validation_exc.status_code,
            content=validation_exc.to_response().model_dump(mode="json"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """
        HTTP 예외 핸들러

        FastAPI/Starlette의 기본 HTTP 예외를 일관된 형식으로 변환합니다.
        """
        logger.warning(
            "[HTTPException] %s: %s",
            exc.status_code,
            exc.detail,
            extra={
                "path": request.url.path,
                "method": request.method,
                "status_code": exc.status_code,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error_code=f"HTTP_{exc.status_code}",
                message=str(exc.detail) if exc.detail else "HTTP 오류가 발생했습니다.",
                detail=None,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """
        일반 예외 핸들러

        처리되지 않은 모든 예외를 캐치하여 500 에러 응답을 반환합니다.
        운영 환경에서는 상세 정보를 숨깁니다.
        """
        # DB 예외는 traceback 을 남기지 않는다.
        #
        # SQLAlchemy 예외의 str() 에는 실행된 SQL 과 바인딩된 값이 들어 있고,
        # traceback 은 그것을 그대로 출력한다. 이 로거 이름은 ``app.core.*`` 이라
        # SqlNoiseFilter 도 통과한다 — 필터로 막아둔 값이 여기로 새던 경로다(F-015).
        #
        # 정상 경로의 DB 예외는 이미 ``convert_db_error`` 가 경계에서 소독한다.
        # 여기 도달했다는 것은 변환기를 거치지 않은 경로가 있다는 뜻이므로,
        # **어떤 종류였는지와 드라이버 코드만** 남겨 그 경로를 찾을 단서를 준다.
        if isinstance(exc, SQLAlchemyError):
            logger.error(
                "[UnhandledException] %s (변환기 미경유 DB 예외, driver_code=%s)",
                type(exc).__name__,
                driver_error_code(exc),
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "exception_type": type(exc).__name__,
                },
            )
        else:
            logger.exception(
                "[UnhandledException] %s",
                type(exc).__name__,
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "exception_type": type(exc).__name__,
                },
            )
        # detail 은 **DEBUG 에서도** 비운다.
        #
        # 잡히지 않은 예외의 대부분은 DB 계층에서 올라온다. SQLAlchemy 의
        # ``str(exc)`` 에는 실행된 SQL 과 **바인딩된 값**, 때로는 DSN 이 그대로 들어
        # 있다 — 그것을 HTTP 응답으로 돌려주면 로그 필터(C-5)로 막아둔 것을 응답
        # 경로로 새로 여는 셈이다. "DEBUG 니까 괜찮다"가 성립하려면 DEBUG 인 서버가
        # 절대 외부에 노출되지 않아야 하는데, 그 전제는 사고로 자주 깨진다.
        #
        # 개발자가 볼 내용은 로그에 있다 — 바로 위 ``logger.exception`` 이 traceback
        # 전체를 남긴다. 외부로는 error code 만 나간다.
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error_code="INTERNAL_SERVER_ERROR",
                message="내부 서버 오류가 발생했습니다.",
                detail=None,
            ).model_dump(mode="json"),
        )


class HealthResponse(BaseModel):
    """헬스체크 응답 스키마"""

    status: str
    version: str


class ReadyResponse(BaseModel):
    """준비 상태(readiness) 응답 스키마"""

    status: str


def _add_health_and_docs(app: FastAPI) -> None:
    """헬스체크 엔드포인트와 Scalar API 문서를 등록합니다."""

    @app.get(
        "/health",
        response_model=HealthResponse,
        tags=["Health"],
        summary="헬스체크",
        description="서버의 정상 동작 여부를 확인합니다.",
        operation_id="healthCheck",
    )
    async def health_check() -> HealthResponse:
        """
        헬스체크 엔드포인트

        Returns:
            서버 상태 정보
        """
        return HealthResponse(
            status="healthy",
            version=app_settings.VERSION,
        )

    # liveness 와 readiness 를 나눈다.
    #
    # `/health` 는 "프로세스가 살아 있는가"만 답한다 — 여기서 DB 를 보면 DB 가
    # 잠깐 흔들릴 때 오케스트레이터가 **멀쩡한 프로세스를 죽인다**.
    # `/ready` 는 "트래픽을 받을 수 있는가"를 답한다. 준비되지 않았으면 재시작이
    # 아니라 로드밸런서에서 빼는 것이 맞는 조치다.
    @app.get(
        "/ready",
        response_model=ReadyResponse,
        tags=["Health"],
        summary="준비 상태(readiness)",
        description=(
            "트래픽을 받을 준비가 됐는지 확인합니다. writer DB 에 `SELECT 1` 을 "
            f"최대 {READINESS_TIMEOUT_SECONDS:.0f}초 안에 실행하고, 실패하거나 "
            "시간을 넘기면 503 을 반환합니다."
        ),
        operation_id="readinessCheck",
        responses={
            503: {
                "model": ErrorResponse,
                "description": "DB 를 사용할 수 없거나 응답이 늦어 준비되지 않음",
            }
        },
    )
    async def readiness_check() -> ReadyResponse:
        """writer DB 를 확인하고 준비 상태를 반환한다."""
        try:
            await ping_writer_db()
        except Exception as exc:
            # 상세는 서버 로그에만 남긴다. 헬스 엔드포인트는 보통 인증 없이 열려
            # 있어, 응답에 DSN·자격증명·드라이버 오류 원문이 실리면 그대로 유출된다.
            logger.warning("[Readiness] DB 준비 확인 실패: %s", type(exc).__name__)
            raise HTTPException(
                status_code=503,
                detail="서비스가 아직 요청을 받을 준비가 되지 않았습니다.",
            ) from exc
        return ReadyResponse(status="ready")

    # Scalar API 문서 (DEBUG 모드에서만 활성화)
    if app_settings.DEBUG:

        @app.get("/docs", include_in_schema=False)
        async def scalar_docs():
            """
            Scalar API 문서 페이지

            OpenAPI 스키마를 기반으로 인터랙티브 API 문서를 제공합니다.

            Note:
                이 엔드포인트는 DEBUG=True일 때만 활성화됩니다.
                운영 환경(DEBUG=False)에서는 보안을 위해 비활성화됩니다.
            """
            return get_scalar_api_reference(
                openapi_url=app.openapi_url,
                title=app_settings.PROJECT_NAME,
            )


def create_app(
    installed_apps: Sequence[str] | None = None,
    registry: Apps | None = None,
    *,
    enable_admin: bool | None = None,
) -> FastAPI:
    """설치된 앱으로 FastAPI 애플리케이션을 조립한다.

    Args:
        installed_apps: 설치할 앱 목록. ``None`` 이면 ``config.INSTALLED_APPS``.
        registry: 사용할 registry. ``None`` 이면 프로세스 전역 registry 를 쓴다.
            테스트는 격리 인스턴스를 주입해 서로의 상태를 오염시키지 않는다(NFR-05).
        enable_admin: Admin 설치 여부. ``None`` 이면 ``app_settings.ADMIN``.

    Returns:
        조립이 끝난 FastAPI 인스턴스.
    """
    apps_list = list(INSTALLED_APPS if installed_apps is None else installed_apps)
    app_registry = default_registry if registry is None else registry
    admin_enabled = app_settings.ADMIN if enable_admin is None else enable_admin

    # 1~2. registry population — FastAPI 생성보다 먼저다. startup 테이블 생성과
    # migration metadata 가 같은 모델 집합을 봐야 한다.
    app_registry.populate(apps_list)

    app = FastAPI(
        title=app_settings.PROJECT_NAME,
        version=app_settings.VERSION,
        description=app_settings.DESCRIPTION,
        openapi_tags=tags_metadata,
        lifespan=lifespan,
        # 응답 직렬화는 FastAPI 기본 경로(Pydantic 이 JSON 바이트를 직접 생성)를 쓴다.
        docs_url=None,  # Swagger UI 비활성화 (Scalar 사용)
        redoc_url=None,  # ReDoc 비활성화 (Scalar 사용)
        openapi_url="/openapi.json" if app_settings.DEBUG else None,
    )

    # 4. 미들웨어 · 예외 핸들러
    CustomCORSMiddleware(app).configure_cors()
    setup_user_info_middleware(app)

    if app_settings.DEBUG:
        logger.info("API 문서 활성화 (DEBUG 모드): /docs, /openapi.json")
    else:
        logger.info("API 문서 비활성화 (운영 모드): /docs, /openapi.json 접근 차단")

    _register_exception_handlers(app)

    # 5. registry 기반 Router 설치 — main.py 에 include_router 한 줄을 더하지 않는다.
    install_routers(app, app_registry)

    # 6. 헬스체크 + Scalar 문서
    _add_health_and_docs(app)

    # 7. Admin — 여기서만 sqladmin 을 부른다(SEC-01).
    app.state.app_registry = app_registry
    if admin_enabled:
        app.state.admin = create_admin(
            app, engine, app_registry, title=f"{app_settings.PROJECT_NAME} Admin"
        )
        logger.info("SQLAdmin 관리자 페이지 활성화 (ADMIN=True): /admin")
    else:
        logger.info("SQLAdmin 관리자 페이지 비활성화 (ADMIN=False): /admin 접근 차단")

    return app
