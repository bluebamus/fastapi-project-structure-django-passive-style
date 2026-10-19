"""사용자 단위 세션 폐기 — 무엇을 지울지 판정 + refresh family·관리 세션 폐기 (admin-session-hardening ADR-008·ADR-009).

판정은 ``revocation_for_change``·``REVOKE_ON_DELETE`` 한 곳에서 두 집합을 함께 돌려준다 — API 경로(``UserService``)와
관리 화면 경로(``UserAdmin`` 훅)·비밀번호 변경 스크립트가 같은 판정을 쓰므로 조건이 갈리지 않는다.

=====================  ==============  ==========
변경                     관리 세션          refresh
=====================  ==============  ==========
비활성화(True→False)     지운다             지운다
슈퍼유저 해제(True→False)  지운다             **유지**
비밀번호 해시 변경          지운다             지운다
삭제                     지운다             지운다
그 밖(이름·이메일 등)       유지              유지
=====================  ==============  ==========

강등에서 refresh 를 남기는 이유: 강등된 사용자는 일반 사용자로 API 를 계속 쓴다. refresh 회전
(``AuthService.refresh``)은 DB 에서 사용자를 다시 읽어 그때의 ``is_superuser`` 로 access 를 발급하므로
(비활성이면 거부), 다음 회전부터 슈퍼유저 권한이 빠진다. 이미 발급된 access 는 만료(15분)까지 유효하다 —
security-ops-hardening ADR-006(사용자 결정)과 같다.

폐기 로직 자체는 각 저장소(``RefreshTokenStore.revoke_user``·``AdminSessionStore.revoke_user``)에 있다 —
``UserSessionRevoker`` 는 판정 결과대로 부르기만 한다. 호출은 모두 **커밋 전**이다. 폐기가 실패하면(Redis 장애)
예외가 커밋을 막아 "DB 는 바뀌었는데 세션은 살아 있는" 상태를 남기지 않는다(fail-closed).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from starlette.types import Scope

from app.core.security.admin_session import AdminSessionStore, store_from_scope
from app.core.security.refresh_store import RefreshTokenStore


@dataclass(frozen=True)
class Revocation:
    """지울 집합 — 관리 세션·refresh family."""

    admin_sessions: bool = False
    refresh: bool = False

    def __bool__(self) -> bool:
        return self.admin_sessions or self.refresh


#: 삭제는 둘 다 지운다.
REVOKE_ON_DELETE = Revocation(admin_sessions=True, refresh=True)

#: 비밀번호 변경(스크립트)도 둘 다 지운다 — 옛 비밀번호로 연 세션·토큰이 남지 않게.
REVOKE_ON_PASSWORD_CHANGE = Revocation(admin_sessions=True, refresh=True)


def revocation_for_change(before: Any, changes: Mapping[str, Any]) -> Revocation:
    """변경 **전** 사용자(``is_active``·``is_superuser``·``hashed_password``)와 바꿀 값으로 지울 집합을 정한다."""
    deactivated = bool(before.is_active) and changes.get("is_active") is False
    demoted = bool(before.is_superuser) and changes.get("is_superuser") is False
    password_changed = (
        "hashed_password" in changes and changes["hashed_password"] != before.hashed_password
    )
    return Revocation(
        admin_sessions=deactivated or demoted or password_changed,
        refresh=deactivated or password_changed,
    )


class UserSessionRevoker:
    """판정된 집합대로 refresh family 와 관리 세션을 폐기한다.

    Args:
        refresh_store: refresh 회전 기록.
        admin_sessions: 관리 세션 저장소 — 관리 화면이 꺼진 앱이면 ``None``(지울 세션이 없다).
    """

    def __init__(
        self, refresh_store: RefreshTokenStore, admin_sessions: AdminSessionStore | None
    ) -> None:
        self.refresh_store = refresh_store
        self.admin_sessions = admin_sessions

    async def revoke(self, user_id: str, revocation: Revocation) -> None:
        if revocation.refresh:
            await self.refresh_store.revoke_user(user_id)
        if revocation.admin_sessions and self.admin_sessions is not None:
            await self.admin_sessions.revoke_user(user_id)


def revoker_from_scope(scope: Scope) -> UserSessionRevoker:
    """관리 화면 요청에서 — 세션 미들웨어가 둔 저장소의 Redis 로 refresh 저장소도 만든다."""
    from app.core.security.dependencies import get_refresh_token_store

    admin_sessions = store_from_scope(scope)
    return UserSessionRevoker(get_refresh_token_store(admin_sessions.redis), admin_sessions)
