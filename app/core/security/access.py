"""뷰 단위 접근 수준 선언과 기본 거부 정책 (access-policy ADR-001~ADR-003).

뷰는 경로 데코레이터의 ``dependencies=[...]`` 에 접근 수준을 **하나** 적는다::

    @router.get("/posts", dependencies=[Public])
    @router.post("/auth/login", dependencies=[PublicWrite])
    @router.get("/users", dependencies=[SuperuserRequired])
    async def create(payload: X, principal: CurrentPrincipal): ...   # 인자 = LoginRequired

함수를 감싸는 데코레이터(Django 의 ``@login_required``)는 쓰지 않는다. FastAPI 는 함수
시그니처를 읽어 주입·검증·OpenAPI 를 만든다 — 감싸면 그 시그니처가 가려진다.

데코레이터만으로는 "선언을 잊은 뷰" 가 열린 채 배포된다. 그래서 ``AccessPolicyGuard`` 가
조립이 끝난 앱의 모든 API 라우트를 훑고, 선언이 없거나 어긋난 라우트가 하나라도 있으면
기동을 멈춘다(기본 거부). 판정은 라우트의 의존성 트리를 재귀로 본다 — 라우터 단위
``dependencies`` 와 핸들러 인자(``CurrentPrincipal``·``SuperuserPrincipal``)도 선언으로 친다.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fastapi import Depends
from fastapi.routing import APIRoute

from app.core.apps.exceptions import ImproperlyConfigured
from app.core.security.dependencies import get_current_principal, require_superuser

if TYPE_CHECKING:  # pragma: no cover - 타입 검사 전용
    from fastapi import FastAPI
    from fastapi.dependencies.models import Dependant


async def public() -> None:
    """표식 — 인증 없는 조회(GET·HEAD·OPTIONS). 아무것도 하지 않는다."""


async def public_write() -> None:
    """표식 — 인증 없는 쓰기를 명시적으로 연다(가입·로그인·refresh·logout)."""


#: 인증 없음 — 안전한 메서드 전용.
Public = Depends(public)
#: 인증 없는 쓰기 — 일부러 연다는 표시.
PublicWrite = Depends(public_write)
#: 인증 필요(401) — ``CurrentPrincipal`` 인자와 같다.
LoginRequired = Depends(get_current_principal)
#: 슈퍼유저 전용(401/403) — ``SuperuserPrincipal`` 인자와 같다.
SuperuserRequired = Depends(require_superuser)

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class AccessLevel(StrEnum):
    PUBLIC = "public"
    PUBLIC_WRITE = "public_write"
    LOGIN = "login"
    SUPERUSER = "superuser"


class AccessPolicyGuard:
    """조립된 앱의 모든 API 라우트가 접근 수준을 정확히 하나 선언했는지 검사한다."""

    def classify(self, dependant: Dependant) -> set[AccessLevel]:
        """의존성 트리에서 찾은 접근 수준. 슈퍼유저는 내부에 로그인을 품으므로 로그인을 지운다."""
        calls = set(self._calls(dependant))
        levels = {
            level
            for call, level in (
                (public, AccessLevel.PUBLIC),
                (public_write, AccessLevel.PUBLIC_WRITE),
                (get_current_principal, AccessLevel.LOGIN),
                (require_superuser, AccessLevel.SUPERUSER),
            )
            if call in calls
        }
        if AccessLevel.SUPERUSER in levels:
            levels.discard(AccessLevel.LOGIN)
        return levels

    def levels(self, app: FastAPI) -> dict[tuple[str, str], set[AccessLevel]]:
        """``(method, path)`` → 판정된 접근 수준 집합(정상이면 원소 하나)."""
        return {
            (method, path): self.classify(dependant)
            for path, methods, dependant in self._api_routes(app.routes)
            for method in sorted(methods)
        }

    def violations(self, app: FastAPI) -> list[str]:
        found = []
        for path, methods, dependant in self._api_routes(app.routes):
            where = f"{','.join(sorted(methods))} {path}"
            levels = self.classify(dependant)
            if not levels:
                found.append(f"{where}: 접근 수준 선언이 없다")
            elif len(levels) > 1:
                names = ", ".join(sorted(levels))
                found.append(f"{where}: 접근 수준을 둘 이상 선언했다({names})")
            elif AccessLevel.PUBLIC in levels and methods - SAFE_METHODS:
                found.append(f"{where}: 쓰기 메서드에 Public — 인증 없는 쓰기는 PublicWrite")
            elif AccessLevel.PUBLIC_WRITE in levels and methods <= SAFE_METHODS:
                found.append(f"{where}: 안전한 메서드에 PublicWrite — 조회는 Public")
        return found

    def verify(self, app: FastAPI) -> None:
        """위반이 하나라도 있으면 전체 목록을 담아 ``ImproperlyConfigured`` 로 기동을 멈춘다."""
        found = self.violations(app)
        if found:
            raise ImproperlyConfigured(
                "접근 수준 정책 위반 — 뷰마다 dependencies=[Public | PublicWrite | "
                "LoginRequired | SuperuserRequired] 중 하나를 선언하세요 "
                "(app/core/security/access.py):\n  " + "\n  ".join(found)
            )

    def _api_routes(self, routes: list[Any]) -> Iterator[tuple[str, set[str], Dependant]]:
        """서빙되는 ``APIRoute`` 를 펼친다. 문서 경로(Starlette ``Route``)·``Mount`` 는 뺀다.

        FastAPI 0.141 은 ``include_router`` 결과를 ``_IncludedRouter`` 로 감싸 두고 평탄화하지
        않는다 — ``effective_route_contexts()`` 가 prefix·라우터 의존성을 합친 실제 모습이다.
        """
        for route in routes:
            if isinstance(route, APIRoute):
                yield route.path, set(route.methods or ()), route.dependant
            elif hasattr(route, "effective_route_contexts"):
                for ctx in route.effective_route_contexts():
                    if isinstance(ctx.original_route, APIRoute) and ctx.dependant is not None:
                        yield ctx.path, set(ctx.methods), ctx.dependant

    def _calls(self, dependant: Dependant) -> Iterator[Any]:
        for sub in dependant.dependencies:
            yield sub.call
            yield from self._calls(sub)
