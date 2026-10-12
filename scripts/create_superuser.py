"""첫 관리자 만들기 — Django ``createsuperuser`` 대응 (service-hardening ADR-019).

    uv run python -m scripts.create_superuser --username admin --email admin@example.com
    printf '%s\\n' "$ADMIN_PASSWORD" | uv run python -m scripts.create_superuser \\
        --username admin --email admin@example.com --password-stdin

배포 전 할 일의 하나다 — 이렇게 만든 계정이 ``/admin`` 로그인 계정이기도 하다(활성 슈퍼유저만
관리 화면에 들어간다, admin-login ADR-001). 마이그레이션은 아무도 슈퍼유저로 만들지 않는다.

* 사용자가 없으면 슈퍼유저로 **만든다**(이메일·비밀번호 필수).
* 이미 있으면 슈퍼유저로 **승격**한다. 비밀번호는 ``--set-password`` 를 줄 때만 바꾼다 —
  승격하려다 기존 비밀번호를 덮어쓰는 사고를 막는다.

비밀번호는 명령행 인자로 받지 않는다(셸 기록·프로세스 목록에 남는다). 터미널에서는
``getpass`` 로 두 번 묻고, 자동화에서는 ``--password-stdin`` 으로 표준 입력 첫 줄을 읽는다.
환경 변수는 읽지 않는다 — 설정은 ``config.py`` 한 곳에서만 읽는다(설정 계약 테스트).

조립은 API 와 같은 부품을 쓴다: ``background_session()`` 세션의 ``UserRepository`` +
core provider 의 ``PasswordHasher``. 커밋은 한 번이다.

종료 코드: 0 성공 · 1 입력 거부(비밀번호 불일치·짧음·이메일 형식·생성 시 이메일 없음) ·
2 인자 오류(argparse).
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import re
import sys
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import TextIO

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import background_session
from app.core.security import PasswordHasher
from app.core.security.dependencies import get_password_hasher
from app.features.user.repositories.user_repository import UserRepository
from app.utils.validators import EMAIL_PATTERN

#: API(``UserCreate``·``RegisterRequest``)와 같은 길이 규칙.
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class SuperuserInputError(Exception):
    """입력이 규칙을 어겼다(종료 코드 1)."""


def read_password(*, from_stdin: bool, stdin: TextIO) -> str:
    """비밀번호를 읽고 길이를 검사한다."""
    if from_stdin:
        password = stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("비밀번호: ")
        if getpass.getpass("비밀번호 확인: ") != password:
            raise SuperuserInputError("비밀번호가 일치하지 않습니다.")
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise SuperuserInputError(
            f"비밀번호는 {MIN_PASSWORD_LENGTH}~{MAX_PASSWORD_LENGTH}자여야 합니다."
        )
    return password


async def ensure_superuser(
    session_factory: SessionFactory,
    hasher: PasswordHasher,
    *,
    username: str,
    email: str | None,
    password: Callable[[], str],
    set_password: bool,
) -> str:
    """슈퍼유저를 만들거나 승격하고 결과를 한 줄로 돌려준다. 커밋은 한 번이다."""
    async with session_factory() as session:
        users = UserRepository(session)
        user = await users.get_by_username(username)
        if user is None:
            if email is None:
                raise SuperuserInputError("새 사용자를 만들려면 --email 이 필요합니다.")
            hashed = await asyncio.to_thread(hasher.hash, password())
            await users.create(
                {
                    "username": username,
                    "email": email,
                    "hashed_password": hashed,
                    "is_superuser": True,
                }
            )
            result = f"슈퍼유저 '{username}' 을(를) 만들었습니다."
        else:
            changes: dict[str, object] = {"is_superuser": True}
            if set_password:
                changes["hashed_password"] = await asyncio.to_thread(hasher.hash, password())
            await users.update(user.id, changes)
            result = f"기존 사용자 '{username}' 을(를) 슈퍼유저로 승격했습니다."
            if set_password:
                result += " 비밀번호도 바꿨습니다."
            if not user.is_active:
                result += " (비활성 계정입니다 — 로그인하려면 활성화가 필요합니다.)"
        await session.commit()
    return result


def main(
    argv: list[str] | None = None,
    *,
    session_factory: SessionFactory = background_session,
    stdin: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.create_superuser",
        description="슈퍼유저를 만들거나 기존 사용자를 승격한다.",
    )
    parser.add_argument("--username", required=True, help="사용자명")
    parser.add_argument("--email", help="이메일(새로 만들 때 필수)")
    parser.add_argument(
        "--password-stdin", action="store_true", help="표준 입력 첫 줄에서 비밀번호를 읽는다"
    )
    parser.add_argument(
        "--set-password",
        action="store_true",
        help="기존 사용자를 승격할 때 비밀번호도 바꾼다(기본: 바꾸지 않음)",
    )
    args = parser.parse_args(argv)

    def _password() -> str:
        return read_password(from_stdin=args.password_stdin, stdin=stdin or sys.stdin)

    try:
        if not 1 <= len(args.username) <= 100:
            raise SuperuserInputError("사용자명은 1~100자여야 합니다.")
        if args.email is not None and not re.match(EMAIL_PATTERN, args.email):
            raise SuperuserInputError("이메일 형식이 올바르지 않습니다.")
        message = asyncio.run(
            ensure_superuser(
                session_factory,
                get_password_hasher(),
                username=args.username,
                email=args.email,
                password=_password,
                set_password=args.set_password,
            )
        )
    except SuperuserInputError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
