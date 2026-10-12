"""비밀번호 해시 — Argon2 + 기존 bcrypt 해시의 점진 이전 (service-hardening ADR-013).

새 해시는 pwdlib 의 Argon2 다(FastAPI 공식 문서가 권하는 현행 방식). 이전 코드가 저장한
bcrypt 해시(``$2`` 접두사)는 **이전 규칙 그대로** 72바이트로 잘라 검증한다 — 그래야 기존
사용자가 같은 비밀번호로 로그인된다. 검증에 성공하면 Argon2 새 해시를 돌려주고, 호출자가
저장한다(로그인할 때 옮겨 가는 점진 이전).

해시·검증은 CPU 를 수십~수백 ms 쓴다. 호출자(서비스)가 ``asyncio.to_thread`` 로 이벤트 루프
밖에서 부른다.
"""

from __future__ import annotations

import bcrypt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

#: 이전 bcrypt 경로의 입력 절단 길이 — bcrypt 는 72바이트 이후를 보지 않는다(5.x 는 거부한다).
_LEGACY_BCRYPT_MAX_BYTES = 72
_LEGACY_BCRYPT_PREFIX = "$2"


class PasswordHasher:
    """비밀번호 해시·검증을 맡는 단일 클래스(프로세스당 하나 — provider 가 만든다).

    생성 시 타이밍 균등화용 Argon2 더미 해시를 한 번 만든다. 사용자가 없거나 비밀번호가
    없는 계정도 같은 비용의 검증을 거치게 해, 응답 시간으로 사용자명 존재를 알 수 없게 한다.
    """

    def __init__(self) -> None:
        self._hash = PasswordHash((Argon2Hasher(),))
        self._dummy_hash = self._hash.hash("constant-time-dummy-password")

    def hash(self, password: str) -> str:
        """비밀번호를 Argon2 로 해시한다."""
        return self._hash.hash(password)

    def verify_and_update(self, password: str, stored: str | None) -> tuple[bool, str | None]:
        """비밀번호를 검증하고, 저장 해시를 바꿔야 하면 새 해시를 함께 돌려준다.

        Args:
            password: 평문 비밀번호.
            stored: 저장된 해시. ``None``(사용자 없음·비밀번호 없는 계정)이면 더미 해시로
                같은 비용을 치르고 실패한다.

        Returns:
            ``(일치 여부, 새 해시 또는 None)``. 새 해시는 bcrypt → Argon2 이전이거나
            Argon2 파라미터가 바뀐 경우에만 있다.
        """
        if stored is None:
            self._hash.verify(password, self._dummy_hash)
            return False, None
        if stored.startswith(_LEGACY_BCRYPT_PREFIX):
            if not _verify_legacy_bcrypt(password, stored):
                return False, None
            return True, self.hash(password)
        try:
            return self._hash.verify_and_update(password, stored)
        except UnknownHashError:
            # 알 수 없는 형식의 저장값 — 일치로 볼 근거가 없다.
            return False, None


def _verify_legacy_bcrypt(password: str, stored: str) -> bool:
    """이전 코드의 규칙(UTF-8 72바이트 절단)으로 bcrypt 해시를 검증한다."""
    try:
        return bool(
            bcrypt.checkpw(
                password.encode("utf-8")[:_LEGACY_BCRYPT_MAX_BYTES], stored.encode("utf-8")
            )
        )
    except (ValueError, TypeError):
        return False
