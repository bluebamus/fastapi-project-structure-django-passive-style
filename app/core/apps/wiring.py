"""설치 앱을 FastAPI·SQLAdmin 에 결선하는 adapter.

**여기부터는 Django 가 아니다.** ``app/core/apps/{config,registry}.py`` 는 Django 의
app loading lifecycle 을 옮긴 것이고, 이 모듈은 그 결과를 이 프로젝트의 웹 계층에
붙이는 확장이다(CR-08). 경계를 파일로 나눠 둔 이유는 두 가지다.

* registry core 가 FastAPI·SQLAdmin 에 의존하지 않는다(NFR-06). Alembic 이나 CLI 가
  registry 를 쓸 때 웹 스택이 딸려오지 않는다.
* ``ADMIN_DISABLED=true`` 에서 sqladmin 이 로드되지 않는다(SEC-01). 아래 admin 함수는 호출될
  때 비로소 ``sqladmin`` 을 import 한다 — module 최상단에 두면 registry 를 쓰는 모든
  진입점이 sqladmin 을 끌고 들어온다.

결선 규칙은 앱의 ``AppConfig`` 가 선언한다. module 이 없는 앱은 그 기능을 제공하지
않는 것으로 보고 건너뛴다. 반면 **module 은 있는데 공개 이름이 없거나 내부 import 가
실패하면 기동을 실패시킨다** — 조용히 건너뛰면 "라우트가 사라졌는데 아무도 모르는"
상태가 된다(SEC-07).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.apps.exceptions import ImproperlyConfigured
from app.core.apps.registry import Apps
from app.utils.logs import get_logger

if TYPE_CHECKING:  # pragma: no cover - 타입 검사 전용
    from fastapi import FastAPI
    from sqladmin import Admin

logger = get_logger("app.core.apps.wiring")

#: SQLAdmin 템플릿 덮어쓰기 디렉터리 — 여기의 ``sqladmin/<이름>.html`` 이 패키지 템플릿보다 먼저다.
ADMIN_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "admin"


def install_routers(app: FastAPI, registry: Apps) -> list[str]:
    """설치 앱의 router 를 ``INSTALLED_APPS`` 순서대로 마운트한다.

    Args:
        app: 조립 중인 FastAPI 인스턴스.
        registry: population 이 끝난 registry.

    Returns:
        router 를 설치한 앱 label 목록(로깅·검증용).

    Raises:
        ImproperlyConfigured: 같은 method+path 를 두 앱이 등록했다.
    """
    installed: list[str] = []
    seen: dict[tuple[str, str], str] = {}

    for config in registry.get_app_configs():
        router = config.import_router()
        if router is None:
            logger.debug("[apps] '%s' 는 router 가 없다 — 건너뜀", config.label)
            continue

        for route in getattr(router, "routes", []):
            path = f"{config.router_prefix}{getattr(route, 'path', '')}"
            for method in sorted(getattr(route, "methods", None) or []):
                key = (method, path)
                if key in seen:
                    raise ImproperlyConfigured(
                        f"route 충돌: {method} {path} 를 앱 '{seen[key]}' 와 "
                        f"'{config.label}' 이 함께 등록합니다. "
                        "config.INSTALLED_APPS 의 순서나 앱의 prefix 를 조정하세요."
                    )
                seen[key] = config.label

        app.include_router(router, prefix=config.router_prefix)
        installed.append(config.label)

    logger.info("[apps] router 설치 완료: %s", installed)
    return installed


def install_admin(admin: Admin, registry: Apps) -> list[str]:
    """설치 앱의 ``admin_views`` 를 선언 순서대로 등록한다.

    목록을 **만들지 않는다** — 등록 대상의 진실은 ``INSTALLED_APPS`` 와 각 앱의
    ``admin.py`` 뿐이다. 디렉터리 스캔도, 예외 무시도 하지 않는다.

    Returns:
        등록된 ModelView 의 model 이름 목록.
    """
    registered: list[str] = []
    for config in registry.get_app_configs():
        views = config.import_admin_views()
        if views is None:
            continue
        for view in views:
            admin.add_view(view)
            registered.append(getattr(getattr(view, "model", None), "__name__", str(view)))

    logger.info("[apps] admin view 등록 완료: %s", registered)
    return registered


def create_admin(app: FastAPI, engine: Any, registry: Apps, *, title: str) -> Admin:
    """SQLAdmin 을 만들어 ``/admin`` 에 마운트하고 설치 앱의 뷰를 등록한다.

    ``sqladmin`` import 가 함수 안에 있는 것이 핵심이다(SEC-01) — ``ADMIN_DISABLED=true`` 인
    프로세스는 이 함수를 부르지 않으므로 sqladmin 도, 앱별 ``admin.py`` 도,
    거기 딸린 ModelView 들도 메모리에 올라오지 않는다.

    ``/admin`` 은 활성 슈퍼유저 로그인이 필요하다(admin-login ADR-001). 인증 백엔드
    (``AdminAuthBackend``)는 여기서 조립해 ``Admin(authentication_backend=...)`` 로 주입한다.
    자격 확인 구현은 설치 앱이 ``ready()`` 에서 등록한 팩토리다(core 는 사용자 모델을 모른다) —
    등록한 앱이 없으면 인증 없는 관리 화면을 여는 대신 기동을 멈춘다. 로그인 화면은
    ``app/templates/admin/sqladmin/login.html`` 이 sqladmin 기본 템플릿을 덮어쓴다
    (``templates_dir`` 의 ``FileSystemLoader`` 가 패키지 템플릿보다 먼저다). 로그인 이후 화면의
    CSRF meta·스크립트는 ``sqladmin/base.html`` 이 원본(``sqladmin_original/base.html``)을 확장해
    더한다. 세션은 Redis 서버 세션이고, 로그아웃은 POST 전용이다(admin-session-hardening ADR-001~003).

    Args:
        app: FastAPI 인스턴스. ``Admin(...)`` 생성 시 SQLAdmin 이 ``/admin`` 을 직접
            마운트한다 — 별도 ``include_router`` 는 필요 없다.
        engine: SQLAlchemy async 엔진.
        registry: population 이 끝난 registry(``ready()`` 까지 끝나 있어야 한다).
        title: 관리 화면 제목.

    Raises:
        ImproperlyConfigured: 자격 확인을 등록한 설치 앱이 없다, 또는 관리 화면 세션 쿠키
            이름이 ``SESSION_COOKIE_NAME`` 과 같다.
    """
    from sqladmin import Admin

    from app.core.middlewares.client_ip import ClientIPResolver
    from app.core.security.admin_auth import (
        AdminAuthBackend,
        AdminLoginLimits,
        AdminSessionCookie,
        require_post_logout,
    )
    from app.core.security.admin_credentials import get_admin_credentials_factory
    from app.core.security.admin_session import default_admin_session_store
    from app.core.security.rate_limit import RateLimiter
    from config import app_settings, jwt_settings, middleware_settings, session_settings

    credentials_factory = get_admin_credentials_factory()
    if credentials_factory is None:
        raise ImproperlyConfigured(
            "관리 화면이 켜져 있는데 로그인의 자격 확인을 등록한 설치 앱이 없습니다. "
            "auth 앱(app.features.auth.apps.AuthConfig)을 INSTALLED_APPS 에 두거나 "
            "ADMIN_DISABLED=true 로 끄세요."
        )
    cookie = AdminSessionCookie(
        https_only=app_settings.ENV in ("staging", "production"),
        max_age=session_settings.ADMIN_SESSION_MAX_AGE_SECONDS,
    )
    if cookie.name == session_settings.SESSION_COOKIE_NAME:
        raise ImproperlyConfigured(
            f"SESSION_COOKIE_NAME 이 관리 화면 세션 쿠키 이름('{cookie.name}')과 같습니다. "
            "접속 로그가 관리자 세션 쿠키를 기록하게 되므로 다른 이름을 쓰세요."
        )

    backend = AdminAuthBackend(
        credentials=credentials_factory(),
        # Redis 는 lifespan 이 기동 때 app.state 에 둔다 — 조립 시점에는 아직 없어 요청 때 꺼낸다.
        rate_limiter=lambda: RateLimiter(app.state.redis),
        ip_resolver=ClientIPResolver(middleware_settings.TRUSTED_PROXY_HOPS),
        limits=AdminLoginLimits(
            per_user=jwt_settings.AUTH_LOGIN_MAX_ATTEMPTS,
            per_ip=jwt_settings.AUTH_LOGIN_IP_MAX_ATTEMPTS,
            window_seconds=jwt_settings.AUTH_LOGIN_WINDOW_SECONDS,
        ),
        # 관리 세션도 같은 Redis 에 둔다(admin-session-hardening ADR-001) — 같은 이유로 요청 때 꺼낸다.
        session_store=lambda: default_admin_session_store(app.state.redis),
        cookie=cookie,
    )
    admin = Admin(
        app,
        engine,
        title=title,
        authentication_backend=backend,
        templates_dir=str(ADMIN_TEMPLATES_DIR),
    )
    backend.templates = admin.templates
    require_post_logout(admin)
    install_admin(admin, registry)
    return admin
