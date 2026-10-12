"""SQLAdmin(``/admin``) 로그인 — 슈퍼유저 세션 인증 (admin-login ADR-001·ADR-002).

``/admin`` 의 모든 화면은 활성 슈퍼유저로 로그인해야 열린다. 쿠키는 서명된 세션
(starlette ``SessionMiddleware`` + itsdangerous, 서명 키는 ``SESSION_SECRET_KEY``)이고 안에는
사용자 id 만 담는다. 권한은 쿠키를 믿지 않고 **매 요청 DB 로 다시 확인**한다 — 강등·비활성화가
다음 요청부터 바로 반영된다.

이 모듈은 sqladmin 을 import 한다. 그래서 ``app.core.security`` 패키지가 다시 내보내지 않고,
``app.core.apps.wiring.create_admin`` 이 관리 화면이 켜져 있을 때만(``ADMIN_DISABLED=false``) 함수 안에서 import 한다(SEC-01).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from sqladmin.authentication import AuthenticationBackend
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.admin_credentials import AdminCredentials
from app.core.security.rate_limit import RateLimiter
from app.utils.logs import get_logger

logger = get_logger("app.core.security.admin_auth")

#: 세션에 담는 유일한 값의 키. sqladmin 의 ``get_user_id`` 기본 구현이 이 키를 읽는다.
SESSION_USER_KEY = "user_id"

#: 로그에 남길 사용자명 최대 길이 — 긴 입력으로 로그를 부풀리지 못하게 자른다.
LOG_USERNAME_MAX = 64

#: 자격 실패는 ``False`` 만 돌려준다 — sqladmin 이 같은 문구로 400 을 그린다. 없는 사용자·틀린
#: 비밀번호·비슈퍼유저·비활성을 구분하지 않는다(계정 열거 차단).
RATE_LIMITED_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."


@dataclass(frozen=True)
class AdminSessionCookie:
    """관리 화면 세션 쿠키 옵션. ``httponly`` 는 ``SessionMiddleware`` 가 항상 붙인다.

    이름은 API 쪽 세션 쿠키(``SESSION_COOKIE_NAME``, 접속 로그가 ``session_id`` 로 기록한다)와
    달라야 한다 — 같으면 관리자 세션 쿠키가 접속 로그에 그대로 남는다.
    """

    https_only: bool
    name: str = "admin_session"
    path: str = "/admin"
    same_site: Literal["lax", "strict", "none"] = "strict"
    max_age: int = 8 * 60 * 60


@dataclass(frozen=True)
class AdminLoginLimits:
    """로그인 레이트 리밋 — API 로그인과 같은 설정값을 쓰고 키 접두사만 나눈다."""

    per_user: int
    per_ip: int
    window_seconds: int


class AdminAuthBackend(AuthenticationBackend):
    """SQLAdmin 인증 백엔드. 협력 객체는 모두 생성자로 받는다.

    Args:
        credentials: 관리자 자격 확인(사용자 기능 쪽 구현이 세션 팩토리·``PasswordHasher`` 를 가진다).
        rate_limiter: 요청 시점에 ``RateLimiter`` 를 돌려주는 provider — Redis 클라이언트는
            lifespan 이 기동 때 만들므로 조립 시점에는 아직 없다.
        ip_resolver: 레이트 리밋·로그의 클라이언트 IP(``TRUSTED_PROXY_HOPS``).
        limits: 시도 한도.
        secret_key: 세션 쿠키 서명 키(``SESSION_SECRET_KEY``).
        cookie: 세션 쿠키 옵션.
    """

    def __init__(
        self,
        *,
        credentials: AdminCredentials,
        rate_limiter: Callable[[], RateLimiter],
        ip_resolver: ClientIPResolver,
        limits: AdminLoginLimits,
        secret_key: str,
        cookie: AdminSessionCookie,
    ) -> None:
        # 부모 생성자는 쿠키 옵션을 고를 수 없는 기본 SessionMiddleware 를 만든다 — 직접 구성한다.
        self.middlewares = [
            Middleware(
                SessionMiddleware,
                secret_key=secret_key,
                session_cookie=cookie.name,
                max_age=cookie.max_age,
                path=cookie.path,
                same_site=cookie.same_site,
                https_only=cookie.https_only,
            )
        ]
        self.credentials = credentials
        self.rate_limiter = rate_limiter
        self.ip_resolver = ip_resolver
        self.limits = limits
        #: 429 화면을 그릴 템플릿 — ``Admin`` 이 만든 것을 조립 지점이 넣는다(생성 순서상 사후 주입).
        self.templates: Any = None

    async def login(self, request: Request) -> Response | bool:
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        ip = self.ip_resolver.resolve(request)
        shown = username[:LOG_USERNAME_MAX]

        limiter = self.rate_limiter()
        user_key = _user_key(ip, username)
        for key, limit in (
            (f"admin-login:ip:{ip}", self.limits.per_ip),
            (user_key, self.limits.per_user),
        ):
            result = await limiter.hit(key, limit, self.limits.window_seconds)
            if not result.allowed:
                logger.warning("[AdminLogin] 시도 한도 초과 ip=%s username=%r", ip, shown)
                return await self._rate_limited(request, result.retry_after)

        user_id = await self.credentials.verify(username, password)
        if user_id is None:
            logger.warning("[AdminLogin] 실패 ip=%s username=%r", ip, shown)
            return False

        # 세션 고정 방지 — 로그인 전에 들고 온 값은 하나도 남기지 않고 id 만 새로 쓴다.
        request.session.clear()
        request.session[SESSION_USER_KEY] = user_id
        await limiter.reset(user_key)
        logger.info("[AdminLogin] 성공 ip=%s user_id=%s", ip, user_id)
        return True

    async def logout(self, request: Request) -> Response | bool:
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        user_id = request.session.get(SESSION_USER_KEY)
        if not isinstance(user_id, str) or not user_id:
            return False
        if not await self.credentials.is_admin(user_id):
            # 강등·비활성화·삭제 — 쿠키가 아직 유효해도 즉시 끊는다.
            request.session.clear()
            logger.warning("[AdminLogin] 세션 거부(더 이상 관리자가 아님) user_id=%s", user_id)
            return False
        return True

    async def _rate_limited(self, request: Request, retry_after: int) -> Response:
        response: Response = await self.templates.TemplateResponse(
            request,
            "sqladmin/login.html",
            {"error": RATE_LIMITED_MESSAGE},
            status_code=429,
        )
        response.headers["Retry-After"] = str(retry_after)
        return response


def _user_key(ip: str, username: str) -> str:
    """ip+username 카운터 키 — API 로그인(``login:user:``)과 접두사가 다르다."""
    digest = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
    return f"admin-login:user:{ip}:{digest}"
