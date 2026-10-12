"""엔드포인트 테스트용 Bearer 헤더 — **실제 토큰**을 발급해 인가 경로 전체를 거친다.

``get_current_principal`` 을 override 하지 않는다. 그러면 토큰 검증·``su`` claim·
``request.state.user_id`` 기록이 테스트에서 빠진다. 여기서는 운영과 같은 provider
(``get_token_service``)로 access 토큰을 발급해 Authorization 헤더로 싣는다.
"""

from __future__ import annotations

from app.core.security.dependencies import get_token_service

ADMIN_ID = "00000000-0000-0000-0000-00000000a0a0"
USER_ID = "00000000-0000-0000-0000-00000000b0b0"
OTHER_ID = "00000000-0000-0000-0000-00000000c0c0"


def bearer(user_id: str, username: str, *, superuser: bool = False) -> dict[str, str]:
    """주어진 주체의 access 토큰을 담은 Authorization 헤더."""
    token = get_token_service().issue_access(user_id, username, superuser).token
    return {"Authorization": f"Bearer {token}"}


def admin_headers() -> dict[str, str]:
    """슈퍼유저 헤더(DB 에 없는 가상 관리자 — 인가는 토큰만 본다)."""
    return bearer(ADMIN_ID, "admin", superuser=True)


def user_headers() -> dict[str, str]:
    """일반 사용자 헤더."""
    return bearer(USER_ID, "alice")


def other_headers() -> dict[str, str]:
    """다른 일반 사용자 헤더."""
    return bearer(OTHER_ID, "mallory")
