"""관리 화면(``/admin``) 세션 — Redis 서버 세션 (admin-session-hardening ADR-001).

쿠키(``admin_session``)에는 무작위 세션 ID 만 담고, 내용은 Redis 에 둔다. 그래서 로그아웃·강등·
비활성화·삭제·비밀번호 변경 때 **서버에서 즉시 폐기**할 수 있다 — 서명 쿠키 시절에는 복사해 둔
쿠키가 만료(8시간)까지 유효했다.

키:
    - ``admin:sess:{HMAC-SHA256(SESSION_SECRET_KEY, sid)}`` → JSON ``{"data", "user_id", "created_at"}``.
      TTL = min(미사용 만료, 절대 만료까지 남은 시간). 요청마다 갱신하되 절대 만료를 넘지 않는다.
      키는 세션 ID 의 HMAC 이라 Redis 키가 새도 쿠키를 만들 수 없다. ``SESSION_SECRET_KEY`` 를 바꾸면
      모든 관리 세션이 무효가 된다(키를 다시 계산할 수 없으므로).
    - ``admin:user_sessions:{user_id}`` → 그 사용자의 세션 키 집합(SET). TTL = 절대 만료. 사용자 단위 폐기용.

두 클래스로 나눈다 — 저장소(``AdminSessionStore``)는 미들웨어·폐기 훅(사용자 기능·스크립트)·테스트가
함께 쓰고, 미들웨어(``RedisSessionMiddleware``)는 ``scope["session"]`` 에 dict 를 넣어
``request.session`` 인터페이스를 그대로 유지한다(인증 백엔드는 세션 저장 방식을 모른다).

이 모듈은 sqladmin 을 import 하지 않는다 — 사용자 기능의 폐기 훅이 ``ADMIN_DISABLED=true`` 에서도
sqladmin 없이 import 한다(SEC-01).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.utils.logs import get_logger

logger = get_logger("app.core.security.admin_session")

#: 세션에 담는 사용자 id 의 키. sqladmin 의 ``get_user_id`` 기본 구현이 이 키를 읽는다.
SESSION_USER_KEY = "user_id"

#: 미들웨어가 요청 scope 에 저장소를 두는 자리 — 관리 뷰의 폐기 훅이 꺼낸다(``store_from_scope``).
STORE_SCOPE_KEY = "admin_session.store"

#: 로그인 성공 시 세션 ID 회전을 요청하는 scope 플래그(``RedisSessionMiddleware.rotate``).
ROTATE_SCOPE_KEY = "admin_session.rotate"

#: Redis 를 쓸 수 없을 때의 응답 문구 — 관리 화면은 fail-closed 다.
UNAVAILABLE_MESSAGE = "관리 세션 저장소(Redis)를 사용할 수 없습니다. 잠시 후 다시 시도하세요."


@dataclass(frozen=True)
class AdminSessionCookie:
    """관리 화면 세션 쿠키 옵션. HttpOnly 는 항상 붙는다.

    이름은 API 쪽 세션 쿠키(``SESSION_COOKIE_NAME``, 접속 로그가 ``session_id`` 로 기록한다)와
    달라야 한다 — 같으면 관리자 세션 ID 가 접속 로그에 그대로 남는다. ``max_age`` 는 절대 만료
    (``ADMIN_SESSION_MAX_AGE_SECONDS``)와 같다.
    """

    https_only: bool
    max_age: int = 8 * 60 * 60
    name: str = "admin_session"
    path: str = "/admin"
    same_site: Literal["lax", "strict", "none"] = "strict"


@dataclass(frozen=True)
class StoredSession:
    """Redis 에서 읽은 세션 하나. ``key`` 는 HMAC 키다(세션 ID 자체는 들고 다니지 않는다)."""

    key: str
    data: dict[str, Any]
    user_id: str | None
    created_at: float


class AdminSessionStore:
    """관리 세션의 저장·조회·삭제·사용자별 전체 폐기.

    Args:
        redis: lifespan 이 소유한 클라이언트.
        secret_key: 세션 ID → Redis 키 HMAC 키(``SESSION_SECRET_KEY``).
        max_age: 절대 만료(초) — 생성 시각 기준, 연장되지 않는다.
        idle: 미사용 만료(초) — 요청마다 다시 센다.
        clock: 현재 시각(epoch 초). 테스트가 바꾼다.
    """

    def __init__(
        self,
        redis: Redis,
        secret_key: str,
        *,
        max_age: int,
        idle: int,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis = redis
        self._secret = secret_key.encode("utf-8")
        self.max_age = max_age
        self.idle = idle
        self._clock = clock

    @property
    def redis(self) -> Redis:
        """이 저장소의 Redis 클라이언트 — 같은 요청의 다른 저장소(refresh 폐기)가 함께 쓴다."""
        return self._redis

    def key_for(self, sid: str) -> str:
        digest = hmac.new(self._secret, sid.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"admin:sess:{digest}"

    async def load(self, sid: str) -> StoredSession | None:
        """세션을 읽는다. 없거나·깨졌거나·절대 만료를 넘었으면 ``None``."""
        key = self.key_for(sid)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            value = json.loads(raw)
            session = StoredSession(
                key, dict(value["data"]), value.get("user_id"), float(value["created_at"])
            )
        except (ValueError, KeyError, TypeError):
            logger.warning("[AdminSession] 해석할 수 없는 세션 값 — 폐기")
            await self._redis.delete(key)
            return None
        if self._clock() >= session.created_at + self.max_age:
            await self.delete(session)
            return None
        return session

    async def create(self, data: dict[str, Any]) -> str:
        """새 세션을 만들고 세션 ID(쿠키 값)를 돌려준다."""
        sid = secrets.token_urlsafe(32)
        session = StoredSession(self.key_for(sid), {}, None, self._clock())
        await self.save(session, data)
        return sid

    async def save(self, session: StoredSession, data: dict[str, Any]) -> None:
        """내용을 쓰고 TTL 을 다시 건다. 사용자가 있으면 사용자별 집합에 넣는다."""
        user_id = data.get(SESSION_USER_KEY)
        user_id = user_id if isinstance(user_id, str) and user_id else None
        value = json.dumps({"data": data, "user_id": user_id, "created_at": session.created_at})
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(session.key, value, ex=self._ttl(session))
            if user_id is not None:
                index = _user_index_key(user_id)
                pipe.sadd(index, session.key)
                pipe.expire(index, self.max_age)
            await pipe.execute()

    async def touch(self, session: StoredSession) -> None:
        """내용은 그대로 두고 미사용 만료만 다시 센다(절대 만료는 넘지 않는다)."""
        await self._redis.expire(session.key, self._ttl(session))

    async def delete(self, session: StoredSession) -> None:
        """세션 하나를 지운다(로그아웃·회전·만료)."""
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.delete(session.key)
            if session.user_id:
                pipe.srem(_user_index_key(session.user_id), session.key)
            await pipe.execute()

    async def revoke_user(self, user_id: str) -> None:
        """그 사용자의 관리 세션을 모두 지운다(비활성화·강등·삭제·비밀번호 변경)."""
        index = _user_index_key(user_id)
        # redis-py 의 타입 표기가 동기·비동기 반환을 합쳐 둔다 — 비동기 클라이언트라 awaitable 이다.
        keys = await self._redis.smembers(index)  # type: ignore[misc]
        await self._redis.delete(index, *keys)

    def _ttl(self, session: StoredSession) -> int:
        remaining = session.created_at + self.max_age - self._clock()
        return max(1, min(self.idle, int(remaining)))


def _user_index_key(user_id: str) -> str:
    return f"admin:user_sessions:{user_id}"


def default_admin_session_store(redis: Redis | None) -> AdminSessionStore:
    """운영 조립 — 키·만료는 ``SessionSettings`` 에서 읽는다(미들웨어·폐기 훅이 같은 값을 쓴다).

    Raises:
        RedisConnectionError: lifespan 밖이라 클라이언트가 없다 — 미들웨어가 503 으로 바꾼다.
    """
    from config import session_settings

    if redis is None:
        raise RedisConnectionError("Redis 클라이언트가 없다(lifespan 밖)")

    return AdminSessionStore(
        redis,
        session_settings.SESSION_SECRET_KEY,
        max_age=session_settings.ADMIN_SESSION_MAX_AGE_SECONDS,
        idle=session_settings.ADMIN_SESSION_IDLE_SECONDS,
    )


def store_from_scope(scope: Scope) -> AdminSessionStore:
    """관리 화면 요청에서 미들웨어가 둔 저장소를 꺼낸다(관리 뷰의 폐기 훅용)."""
    store: AdminSessionStore = scope[STORE_SCOPE_KEY]
    return store


class RedisSessionMiddleware:
    """``scope["session"]`` 을 Redis 세션으로 채우고, 응답 직전에 저장·회전·삭제한다.

    * 쿠키의 세션 ID 가 Redis 에 없으면(만료·폐기) 빈 세션으로 다루고 쿠키를 지운다.
    * 세션이 비면(로그아웃) Redis 키를 지우고 쿠키를 지운다.
    * ``rotate`` 가 요청되면(로그인 성공) 새 세션 ID 를 발급하고 이전 키를 지운다(세션 고정 방지).
    * Redis 를 쓸 수 없으면 통과시키지 않는다 — 503(fail-closed). 응답 직전 저장(쿠키 없는 첫 요청의 세션
      생성 등)이 실패해도 앱이 만든 응답 대신 같은 503 을 낸다(e2e-policy-2 결정 6) — 응답 시작 전이라 바꿀 수 있다.

    Args:
        store: 요청 시점에 저장소를 돌려주는 provider — Redis 는 lifespan 이 기동 때 만든다.
        cookie: 쿠키 옵션.
    """

    def __init__(
        self, app: ASGIApp, *, store: Callable[[], AdminSessionStore], cookie: AdminSessionCookie
    ) -> None:
        self.app = app
        self.store = store
        self.cookie = cookie

    @staticmethod
    def rotate(scope: Scope) -> None:
        """이 요청의 응답에서 세션 ID 를 새로 발급하게 한다(로그인 성공 시 백엔드가 부른다)."""
        scope[ROTATE_SCOPE_KEY] = True

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def unavailable(exc: RedisError) -> None:
            logger.error(
                "[AdminSession] Redis 사용 불가 — 관리 화면 요청 거부(%s)", type(exc).__name__
            )
            await PlainTextResponse(UNAVAILABLE_MESSAGE, status_code=503)(scope, receive, send)

        sid = HTTPConnection(scope).cookies.get(self.cookie.name) or None
        try:
            store = self.store()
            loaded = await store.load(sid) if sid else None
        except RedisError as exc:
            await unavailable(exc)
            return

        scope["session"] = dict(loaded.data) if loaded else {}
        scope[STORE_SCOPE_KEY] = store
        replaced = False

        async def send_wrapper(message: Message) -> None:
            nonlocal replaced
            if replaced:
                return  # 503 으로 바꾼 응답의 나머지 본문은 버린다
            if message["type"] == "http.response.start":
                try:
                    await self._commit(scope, store, sid, loaded, MutableHeaders(scope=message))
                except RedisError as exc:
                    replaced = True
                    await unavailable(exc)
                    return
            await send(message)

        await self.app(scope, receive, send_wrapper)

    async def _commit(
        self,
        scope: Scope,
        store: AdminSessionStore,
        sid: str | None,
        loaded: StoredSession | None,
        headers: MutableHeaders,
    ) -> None:
        session: dict[str, Any] = scope["session"]
        if loaded is not None and (scope.get(ROTATE_SCOPE_KEY) or not session):
            await store.delete(loaded)
            loaded = None
        if session:
            if loaded is None:
                headers.append("set-cookie", self._cookie(await store.create(session)))
            elif session != loaded.data:
                await store.save(loaded, session)
            else:
                await store.touch(loaded)
        elif sid:
            headers.append("set-cookie", self._cookie(""))

    def _cookie(self, value: str) -> str:
        max_age = self.cookie.max_age if value else 0
        parts = [
            f"{self.cookie.name}={value}",
            f"path={self.cookie.path}",
            f"Max-Age={max_age}",
            "httponly",
            f"samesite={self.cookie.same_site}",
        ]
        if not value:
            parts.append("expires=Thu, 01 Jan 1970 00:00:00 GMT")
        if self.cookie.https_only:
            parts.append("secure")
        return "; ".join(parts)
