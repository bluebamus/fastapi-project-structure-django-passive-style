"""SQLAdmin(``/admin``) 로그인 — 슈퍼유저 세션 인증 (admin-login ADR-001·ADR-002).

``/admin`` 의 모든 화면은 활성 슈퍼유저로 로그인해야 열린다. 세션은 Redis 서버 세션이다
(``app.core.security.admin_session`` — 쿠키에는 무작위 세션 ID 만, admin-session-hardening ADR-001).
권한은 세션을 믿지 않고 **매 요청 DB 로 다시 확인**한다 — 강등·비활성화가 다음 요청부터 바로
반영된다(세션 즉시 폐기와 이중 방어).

상태를 바꾸는 모든 관리 요청(POST·PUT·PATCH·DELETE — 로그인·생성·수정·삭제·일괄 삭제·가져오기·
로그아웃)은 ``AdminCsrfMiddleware`` 가 세션의 CSRF 토큰과 대조한다(admin-session-hardening ADR-002).
로그아웃은 POST 전용이다(``require_post_logout``, ADR-003).

이 모듈은 sqladmin 을 import 한다. 그래서 ``app.core.security`` 패키지가 다시 내보내지 않고,
``app.core.apps.wiring.create_admin`` 이 관리 화면이 켜져 있을 때만(``ADMIN_DISABLED=false``) 함수 안에서 import 한다(SEC-01).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.middlewares.client_ip import ClientIPResolver
from app.core.security.admin_credentials import AdminCredentials
from app.core.security.admin_session import (
    SESSION_USER_KEY,
    AdminSessionCookie,
    AdminSessionStore,
    RedisSessionMiddleware,
)
from app.core.security.rate_limit import RateLimiter
from app.utils.logs import get_logger

logger = get_logger("app.core.security.admin_auth")

__all__ = [
    "CSRF_FAILED_MESSAGE",
    "RATE_LIMITED_MESSAGE",
    "SESSION_USER_KEY",
    "AdminAuthBackend",
    "AdminCsrf",
    "AdminCsrfMiddleware",
    "AdminLoginLimits",
    "AdminSessionCookie",
    "require_post_logout",
]

#: 로그에 남길 사용자명 최대 길이 — 긴 입력으로 로그를 부풀리지 못하게 자른다.
LOG_USERNAME_MAX = 64

#: 자격 실패는 ``False`` 만 돌려준다 — sqladmin 이 같은 문구로 400 을 그린다. 없는 사용자·틀린
#: 비밀번호·비슈퍼유저·비활성을 구분하지 않는다(계정 열거 차단).
RATE_LIMITED_MESSAGE = "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요."

#: CSRF 토큰이 없거나 맞지 않을 때의 문구 — 자격 확인을 하지 않았으므로 자격 이야기는 하지 않는다.
CSRF_FAILED_MESSAGE = "요청이 만료되었습니다. 다시 시도하세요."

#: 토큰을 보지 않는 메서드 — 조회는 상태를 바꾸지 않는다. sqladmin 0.32 의 GET 라우트는 모두
#: 조회다(단, ``@action`` 사용자 정의 작업은 GET 이다 — 이 저장소는 쓰지 않는다, ADR-002).
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

_FORM_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


class AdminCsrf:
    """관리 화면 CSRF 토큰 — synchronizer token 패턴.

    security-ops-hardening ADR-004(로그인 폼)를 admin-session-hardening ADR-002 가 로그인 이후
    화면 전체로 넓혔다. 토큰은 관리 세션(Redis)에 하나 두고, 로그인 화면은 hidden 입력으로,
    로그인 이후 화면은 ``<meta name="csrf-token">`` 으로 싣는다 — 덮어쓴 ``sqladmin/base.html`` 의
    스크립트가 POST 폼에는 hidden ``csrf_token`` 을, 같은 출처 ``fetch``·XHR 에는 ``X-CSRF-Token``
    헤더를 붙인다. 다른 사이트는 이 화면을 읽을 수 없으므로 토큰을 모른다. 로그인에 성공하면
    세션을 비우고 새 토큰을 만든다(회전). 세션에 토큰이 없으면 거부한다.
    """

    SESSION_KEY = "csrf_token"
    FORM_FIELD = "csrf_token"
    HEADER = "x-csrf-token"

    @classmethod
    def token_for(cls, request: Request) -> str:
        """세션의 토큰을 돌려준다 — 없으면 만들어 세션에 둔다. 템플릿이 부른다."""
        token = request.session.get(cls.SESSION_KEY)
        if not isinstance(token, str) or not token:
            token = secrets.token_urlsafe(32)
            request.session[cls.SESSION_KEY] = token
        return token

    @classmethod
    def is_valid(cls, request: Request, submitted: object) -> bool:
        """요청 값이 세션 토큰과 같은지 상수 시간으로 비교한다. 둘 중 하나라도 없으면 거부."""
        expected = request.session.get(cls.SESSION_KEY)
        if not isinstance(expected, str) or not expected or not isinstance(submitted, str):
            return False
        return hmac.compare_digest(submitted.encode("utf-8"), expected.encode("utf-8"))


class AdminCsrfMiddleware:
    """``/admin`` 아래 상태를 바꾸는 모든 요청의 CSRF 토큰을 검사한다(로그인 포함 — 검사는 여기 하나).

    토큰 위치는 헤더 ``X-CSRF-Token`` 또는 폼 필드 ``csrf_token``. 폼에서 읽을 때는 본문을 한 번
    버퍼링해 파싱하고, 다운스트림(sqladmin)에는 같은 본문을 ``receive`` 로 다시 흘려 준다 —
    미들웨어가 본문을 그냥 소비하면 다운스트림이 폼을 다시 읽지 못한다. 헤더가 있으면 본문을
    읽지 않는다(``fetch``·XHR 로 보내는 삭제·가져오기).

    Args:
        on_failure: 실패 응답을 만든다(로그인은 로그인 화면 403, 그 밖은 관리 화면 오류 403).
    """

    def __init__(
        self, app: ASGIApp, *, on_failure: Callable[[Request], Awaitable[Response]]
    ) -> None:
        self.app = app
        self.on_failure = on_failure

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        submitted: object = request.headers.get(AdminCsrf.HEADER)
        content_type = request.headers.get("content-type", "")
        if submitted is None and content_type.startswith(_FORM_TYPES):
            # ponytail: 본문 전체를 메모리에 둔다 — 관리 폼 크기면 충분하다(CSV 가져오기는 헤더 경로).
            body = await _read_body(receive)
            receive = _replay(body, receive)
            async with Request(scope, _replay(body, receive)).form() as form:
                submitted = form.get(AdminCsrf.FORM_FIELD)

        if not AdminCsrf.is_valid(request, submitted):
            logger.warning("[AdminCsrf] 토큰 불일치 %s %s", scope["method"], request.url.path)
            response = await self.on_failure(Request(scope, receive))
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay(body: bytes, receive: Receive) -> Receive:
    """버퍼링한 본문을 한 번 돌려주고, 그 뒤로는 원래 ``receive``(연결 끊김 감지)로 넘긴다."""
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return replay


def require_post_logout(admin: Admin) -> None:
    """sqladmin 의 GET 로그아웃 라우트를 POST 전용으로 바꾼다(ADR-003).

    GET 로그아웃은 다른 사이트가 ``<img src>`` 로 강제 로그아웃시킬 수 있다. POST 로 바꾸면
    ``AdminCsrfMiddleware`` 가 토큰을 요구하고, GET 은 405 다. 화면의 로그아웃 링크는 덮어쓴
    ``sqladmin/base.html`` 의 스크립트가 토큰을 실은 POST 폼으로 보낸다.

    Raises:
        RuntimeError: sqladmin 라우트 구조가 바뀌어 ``logout`` 라우트를 찾지 못했다(업그레이드 감지).
    """
    routes = admin.admin.router.routes
    for index, route in enumerate(routes):
        if isinstance(route, Route) and route.name == "logout":
            routes[index] = Route(
                route.path, endpoint=admin.logout, name="logout", methods=["POST"]
            )
            return
    raise RuntimeError("sqladmin 에 logout 라우트가 없다 — 버전이 바뀌었는지 확인하라")


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
        session_store: 요청 시점에 관리 세션 저장소를 돌려주는 provider(같은 이유로 지연).
        cookie: 세션 쿠키 옵션.
    """

    def __init__(
        self,
        *,
        credentials: AdminCredentials,
        rate_limiter: Callable[[], RateLimiter],
        ip_resolver: ClientIPResolver,
        limits: AdminLoginLimits,
        session_store: Callable[[], AdminSessionStore],
        cookie: AdminSessionCookie,
    ) -> None:
        # 부모 생성자는 서명 쿠키 SessionMiddleware 를 만든다 — 부르지 않고 직접 구성한다.
        # 순서가 계약이다: 세션이 바깥(먼저), CSRF 가 안쪽 — CSRF 는 세션의 토큰을 읽는다.
        self.middlewares = [
            Middleware(RedisSessionMiddleware, store=session_store, cookie=cookie),
            Middleware(AdminCsrfMiddleware, on_failure=self.csrf_failed),
        ]
        self.credentials = credentials
        self.rate_limiter = rate_limiter
        self.ip_resolver = ip_resolver
        self.limits = limits
        self._templates: Any = None

    @property
    def templates(self) -> Any:
        """429·403 화면을 그릴 템플릿 — ``Admin`` 이 만든 것을 조립 지점이 넣는다(생성 순서상 사후 주입)."""
        return self._templates

    @templates.setter
    def templates(self, templates: Any) -> None:
        # 로그인 화면(GET 은 sqladmin 이 컨텍스트 없이 그린다)과 덮어쓴 base.html 의 meta 가
        # ``csrf_token(request)`` 로 토큰을 얻게 전역 함수를 건다 — 템플릿을 넣는 순간 함께 걸린다.
        self._templates = templates
        if templates is not None:
            templates.env.globals["csrf_token"] = AdminCsrf.token_for

    async def login(self, request: Request) -> Response | bool:
        # CSRF 는 AdminCsrfMiddleware 가 이미 봤다 — 레이트 리밋보다 먼저라 위조 요청이 피해자의
        # 시도 한도를 깎지 못한다.
        form = await request.form()
        ip = self.ip_resolver.resolve(request)
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
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

        # 세션 고정 방지 — 로그인 전에 들고 온 값은 하나도 남기지 않고, 세션 ID 도 새로 받는다
        # (미들웨어가 이전 Redis 키를 지운다). CSRF 토큰도 새로 만든다(회전).
        request.session.clear()
        request.session[SESSION_USER_KEY] = user_id
        AdminCsrf.token_for(request)
        RedisSessionMiddleware.rotate(request.scope)
        await limiter.reset(user_key)
        logger.info("[AdminLogin] 성공 ip=%s user_id=%s", ip, user_id)
        return True

    async def logout(self, request: Request) -> Response | bool:
        # 세션을 비우면 미들웨어가 Redis 키를 지우고 쿠키를 지운다 — 복사해 둔 쿠키도 죽는다.
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        user_id = request.session.get(SESSION_USER_KEY)
        if not isinstance(user_id, str) or not user_id:
            return False
        if not await self.credentials.is_admin(user_id):
            # 강등·비활성화·삭제 — 세션이 아직 살아 있어도 즉시 끊는다.
            request.session.clear()
            logger.warning("[AdminLogin] 세션 거부(더 이상 관리자가 아님) user_id=%s", user_id)
            return False
        return True

    async def csrf_failed(self, request: Request) -> Response:
        """CSRF 실패 응답 — 로그인은 로그인 화면(403), 그 밖은 관리 화면 맥락의 오류(403).

        로그인하지 않은 요청에는 관리 화면 레이아웃(메뉴에 모델 이름이 나온다)을 그리지 않고 문구만 낸다.
        """
        if request.url.path.rstrip("/").endswith("/login"):
            return await self._render_login(request, CSRF_FAILED_MESSAGE, 403)
        if not request.session.get(SESSION_USER_KEY):
            return PlainTextResponse(CSRF_FAILED_MESSAGE, status_code=403)
        response: Response = await self.templates.TemplateResponse(
            request,
            "sqladmin/error.html",
            {"status_code": 403, "message": CSRF_FAILED_MESSAGE},
            status_code=403,
        )
        return response

    async def _rate_limited(self, request: Request, retry_after: int) -> Response:
        response = await self._render_login(request, RATE_LIMITED_MESSAGE, 429)
        response.headers["Retry-After"] = str(retry_after)
        return response

    async def _render_login(self, request: Request, error: str, status_code: int) -> Response:
        response: Response = await self.templates.TemplateResponse(
            request, "sqladmin/login.html", {"error": error}, status_code=status_code
        )
        return response


def _user_key(ip: str, username: str) -> str:
    """ip+username 카운터 키 — API 로그인(``login:user:``)과 접두사가 다르다."""
    digest = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()
    return f"admin-login:user:{ip}:{digest}"
