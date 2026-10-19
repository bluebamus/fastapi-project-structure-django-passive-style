"""폐기 판정 ``revocation_for_change`` — 관리 세션·refresh 두 집합을 한 곳에서 (admin-session-hardening ADR-010)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.security.revocation import (
    REVOKE_ON_DELETE,
    REVOKE_ON_PASSWORD_CHANGE,
    Revocation,
    revocation_for_change,
)

ADMIN = SimpleNamespace(is_active=True, is_superuser=True, hashed_password="h1")
INACTIVE_USER = SimpleNamespace(is_active=False, is_superuser=False, hashed_password="h1")


@pytest.mark.parametrize(
    ("before", "changes", "expected"),
    [
        (ADMIN, {"is_active": False}, Revocation(admin_sessions=True, refresh=True)),
        (ADMIN, {"is_superuser": False}, Revocation(admin_sessions=True, refresh=True)),
        (ADMIN, {"hashed_password": "h2"}, Revocation(admin_sessions=True, refresh=True)),
        (ADMIN, {"hashed_password": "h1"}, Revocation()),
        (ADMIN, {"email": "x@y.z", "is_active": True, "is_superuser": True}, Revocation()),
        (INACTIVE_USER, {"is_active": False, "is_superuser": False}, Revocation()),
    ],
    ids=["deactivate", "demote", "password", "same-password", "plain", "already-off"],
)
def test_one_judgement_gives_both_sets(before, changes, expected):
    assert revocation_for_change(before, changes) == expected


def test_delete_and_password_change_revoke_both():
    both = Revocation(admin_sessions=True, refresh=True)

    assert REVOKE_ON_DELETE == both
    assert REVOKE_ON_PASSWORD_CHANGE == both
    assert not Revocation()
