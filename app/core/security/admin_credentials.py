"""/admin 로그인의 자격 확인 계약과 등록 훅 (admin-login ADR-002).

core 는 사용자 모델을 모른다(계층 규칙 — core 는 features 를 import 하지 않는다). 그래서
관리 화면 인증 백엔드(``app.core.security.admin_auth.AdminAuthBackend``)는 "이 사용자명·
비밀번호가 관리자인가", "이 id 가 아직 관리자인가" 두 질문만 하고, 답은 사용자 기능을 아는
설치 앱이 ``AppConfig.ready()`` 에서 이 훅으로 등록한 구현이 한다 — 접속 로그 sink
(``app.core.middlewares.access_log_sink``)와 같은 방식이다.

등록하는 것은 인스턴스가 아니라 **팩토리**다. ``ready()`` 는 Alembic·CLI·Celery 에서도 돌므로
여기서 해시기(Argon2 더미 해시 생성)를 만들지 않고, 관리 화면(``ADMIN_DISABLED=false``)을 조립할 때만
부른다. 이 모듈은 sqladmin 을 import 하지 않는다 — ``ADMIN_DISABLED=true`` 에서 sqladmin 이 로드되지
않는 계약(SEC-01)을 지킨다.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol


class AdminCredentials(Protocol):
    """관리자 자격 확인. 구현은 사용자 저장소를 아는 설치 앱이 제공한다."""

    async def verify(self, username: str, password: str) -> str | None:
        """활성 슈퍼유저이고 비밀번호가 맞으면 사용자 id, 아니면 ``None``(사유를 구분하지 않는다)."""
        ...

    async def is_admin(self, user_id: str) -> bool:
        """그 id 가 지금도 활성 슈퍼유저인가 — 매 요청 DB 를 본다(강등·비활성화 즉시 반영)."""
        ...


AdminCredentialsFactory = Callable[[], AdminCredentials]

_factory: AdminCredentialsFactory | None = None


def register_admin_credentials(factory: AdminCredentialsFactory) -> None:
    """자격 확인 구현의 팩토리를 등록한다(설치 앱의 ``ready()`` 가 부른다)."""
    global _factory
    _factory = factory


def get_admin_credentials_factory() -> AdminCredentialsFactory | None:
    """등록된 팩토리. 아무 앱도 등록하지 않았으면 ``None`` — 조립 지점이 기동을 멈춘다."""
    return _factory
