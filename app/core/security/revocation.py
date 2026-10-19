"""사용자 단위 세션 폐기 — refresh family + 관리 화면 세션 (admin-session-hardening ADR-005).

비활성화·슈퍼유저 해제·비밀번호 변경·삭제 때 그 사용자가 가진 **모든** 로그인 상태를 지운다. API
경로(``UserService``)와 관리 화면 경로(``UserAdmin`` 훅)가 이 클래스 하나를 쓰므로 폐기 집합이 같다.
폐기 로직 자체는 각 저장소(``RefreshTokenStore.revoke_user``·``AdminSessionStore.revoke_user``)에 있다 —
여기는 둘을 묶기만 한다.

호출 지점은 모두 **커밋 전**이다. 폐기가 실패하면(Redis 장애) 예외가 커밋을 막아 "DB 는 비활성화됐는데
세션은 살아 있는" 상태를 남기지 않는다(fail-closed).
"""

from __future__ import annotations

from starlette.types import Scope

from app.core.security.admin_session import AdminSessionStore, store_from_scope
from app.core.security.refresh_store import RefreshTokenStore


class UserSessionRevoker:
    """refresh family 와 관리 세션을 함께 폐기한다.

    Args:
        refresh_store: refresh 회전 기록.
        admin_sessions: 관리 세션 저장소 — 관리 화면이 꺼진 앱이면 ``None``(지울 세션이 없다).
    """

    def __init__(
        self, refresh_store: RefreshTokenStore, admin_sessions: AdminSessionStore | None
    ) -> None:
        self.refresh_store = refresh_store
        self.admin_sessions = admin_sessions

    async def revoke(self, user_id: str) -> None:
        await self.refresh_store.revoke_user(user_id)
        if self.admin_sessions is not None:
            await self.admin_sessions.revoke_user(user_id)


def revoker_from_scope(scope: Scope) -> UserSessionRevoker:
    """관리 화면 요청에서 — 세션 미들웨어가 둔 저장소의 Redis 로 refresh 저장소도 만든다."""
    from app.core.security.dependencies import get_refresh_token_store

    admin_sessions = store_from_scope(scope)
    return UserSessionRevoker(get_refresh_token_store(admin_sessions.redis), admin_sessions)
