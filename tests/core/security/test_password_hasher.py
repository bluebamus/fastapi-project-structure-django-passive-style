"""PasswordHasher — Argon2 해시와 bcrypt 점진 이전 (service-hardening ADR-013)."""

import bcrypt
import pytest

from app.core.security import PasswordHasher


@pytest.fixture(scope="module")
def hasher() -> PasswordHasher:
    return PasswordHasher()


def _legacy_bcrypt(password: str) -> str:
    """이전 코드(app/utils/authenticator)가 저장하던 형식 — 72바이트 절단 후 bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt(rounds=4)).decode()


def test_hash_is_argon2_and_verifies(hasher):
    hashed = hasher.hash("s3cret-pw")

    assert hashed.startswith("$argon2id$")
    assert hasher.verify_and_update("s3cret-pw", hashed) == (True, None)
    assert hasher.verify_and_update("wrong", hashed) == (False, None)


def test_legacy_bcrypt_hash_verifies_and_returns_argon2_rehash(hasher):
    legacy = _legacy_bcrypt("old-password")

    ok, new_hash = hasher.verify_and_update("old-password", legacy)

    assert ok is True
    assert new_hash is not None and new_hash.startswith("$argon2id$")
    assert hasher.verify_and_update("old-password", new_hash) == (True, None)


def test_legacy_bcrypt_wrong_password_is_rejected_without_rehash(hasher):
    assert hasher.verify_and_update("nope", _legacy_bcrypt("old-password")) == (False, None)


def test_legacy_bcrypt_keeps_the_72_byte_truncation_rule(hasher):
    """이전 규칙은 72바이트 이후를 무시했다 — 같은 비밀번호로 계속 로그인돼야 한다."""
    long_pw = "a" * 200
    legacy = _legacy_bcrypt(long_pw)

    ok, new_hash = hasher.verify_and_update(long_pw, legacy)

    assert ok is True and new_hash is not None


def test_argon2_does_not_truncate_long_passwords(hasher):
    hashed = hasher.hash("a" * 100)

    assert hasher.verify_and_update("a" * 99 + "b", hashed) == (False, None)


def test_missing_hash_pays_the_dummy_cost_and_fails(hasher, monkeypatch):
    """사용자가 없어도 검증 비용을 치른다(타이밍 균등화)."""
    calls = []
    original = hasher._hash.verify
    monkeypatch.setattr(hasher._hash, "verify", lambda *a: calls.append(a) or original(*a))

    assert hasher.verify_and_update("whatever", None) == (False, None)
    assert len(calls) == 1 and calls[0][1].startswith("$argon2id$")


@pytest.mark.parametrize("stored", ["", "not-a-hash", "$2b$broken"])
def test_unknown_or_broken_hash_is_rejected(hasher, stored):
    assert hasher.verify_and_update("pw", stored) == (False, None)
