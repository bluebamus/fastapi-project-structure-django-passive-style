"""관리자 전용 API 접근 제어."""

from app.utils.authenticator.auth import bearer_scheme, require_admin

__all__ = ["bearer_scheme", "require_admin"]
