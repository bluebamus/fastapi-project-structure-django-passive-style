"""인가 판정 — 상태 없는 ``Principal`` 과 소유권 ``OwnershipPolicy`` (service-hardening ADR-017·ADR-018).

``Principal`` 은 검증된 access 토큰의 claims 만으로 만든다(DB 조회 없음). 기능은 이 값과
``OwnershipPolicy`` 만 알면 되므로 인가를 위해 user 기능을 import 하지 않는다(C-11).

권한은 슈퍼유저/일반 2단계다(ADR-019). 소유자 판정은 ``OwnershipPolicy`` 한 곳에서만 한다 —
기능마다 같은 비교를 흩어 두면 하나가 빠진다.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.exception import ForbiddenException


@dataclass(frozen=True, slots=True)
class Principal:
    """인증된 요청의 주체.

    Attributes:
        id: 사용자 ID(토큰의 ``sub``).
        username: 사용자명(토큰의 ``username``) — 작성자 표시 이름으로 서버가 채운다.
        is_superuser: 슈퍼유저 여부(토큰의 ``su``). 토큰 수명(기본 15분) 동안 유지된다.
    """

    id: str
    username: str
    is_superuser: bool


class OwnershipPolicy:
    """리소스 수정·삭제 권한을 판정한다(프로세스당 하나 — provider 가 만든다)."""

    def ensure_can_modify(self, owner_id: str | None, principal: Principal) -> None:
        """소유자이거나 슈퍼유저면 통과, 아니면 403.

        Args:
            owner_id: 리소스의 소유자 ID. ``None``(소유자 기록 이전에 만든 행)이면 슈퍼유저만
                수정할 수 있다.
            principal: 요청 주체.

        Raises:
            ForbiddenException: 소유자도 슈퍼유저도 아님.
        """
        if principal.is_superuser:
            return
        if owner_id is None or owner_id != principal.id:
            raise ForbiddenException()
