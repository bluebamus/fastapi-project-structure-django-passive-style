"""``scripts/create_superuser.py`` — 생성·승격·비밀번호 규칙·종료 코드 (service-hardening ADR-019).

``main()`` 을 그대로 부르고 세션 팩토리만 SQLite 파일 DB 로 바꾼다. 스크립트가
``asyncio.run`` 으로 새 루프를 만들므로 엔진도 그 루프 안(팩토리 호출 시점)에서 만든다.
"""

from __future__ import annotations

import io
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.db.session import Base
from app.core.security.dependencies import get_password_hasher
from app.features.user.models.models import User
from scripts import create_superuser

PASSWORD = "admin-pw-123"


@pytest.fixture
def db(tmp_path):
    """(세션 팩토리, 동기 엔진) — 테이블은 users 만 만든다."""
    path = (tmp_path / "su.db").as_posix()
    sync_engine = sa.create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync_engine, tables=[User.__table__])

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                yield session
        finally:
            await engine.dispose()

    yield factory, sync_engine
    sync_engine.dispose()


def _users(engine: sa.Engine) -> list[sa.Row]:
    with engine.connect() as connection:
        return list(
            connection.execute(
                sa.select(
                    User.__table__.c.username,
                    User.__table__.c.email,
                    User.__table__.c.is_superuser,
                    User.__table__.c.hashed_password,
                )
            )
        )


def _run(factory, *argv: str, stdin: str = f"{PASSWORD}\n") -> int:
    return create_superuser.main(list(argv), session_factory=factory, stdin=io.StringIO(stdin))


def test_creates_a_superuser_with_an_argon2_hash(db, capsys):
    factory, engine = db

    code = _run(factory, "--username", "root", "--email", "root@x.com", "--password-stdin")

    assert code == 0
    [(username, email, is_superuser, hashed)] = _users(engine)
    assert (username, email, is_superuser) == ("root", "root@x.com", True)
    assert hashed.startswith("$argon2")
    assert get_password_hasher().verify_and_update(PASSWORD, hashed)[0] is True
    assert "root" in capsys.readouterr().out


def test_promotes_an_existing_user_without_touching_the_password(db):
    factory, engine = db
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO users (id, username, email, hashed_password, is_active, "
                "is_superuser, created_at, updated_at) VALUES ('u1', 'alice', 'a@x.com', "
                "'keep-me', 1, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
            )
        )

    code = _run(factory, "--username", "alice", stdin="")

    assert code == 0
    [(_, _, is_superuser, hashed)] = _users(engine)
    assert (is_superuser, hashed) == (True, "keep-me")


def test_set_password_rehashes_when_promoting(db):
    factory, engine = db
    _run(factory, "--username", "bob", "--email", "b@x.com", "--password-stdin")

    code = _run(
        factory, "--username", "bob", "--set-password", "--password-stdin", stdin="new-pass-456\n"
    )

    assert code == 0
    [(_, _, _, hashed)] = _users(engine)
    assert get_password_hasher().verify_and_update("new-pass-456", hashed)[0] is True


def test_interactive_password_must_match(db, monkeypatch):
    factory, engine = db
    answers = iter(["first-pass-1", "other-pass-2"])
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": next(answers))

    code = _run(factory, "--username", "root", "--email", "r@x.com")

    assert code == 1
    assert _users(engine) == [], "거부된 입력이 커밋됐다"


def test_interactive_password_is_accepted_when_confirmed(db, monkeypatch):
    factory, engine = db
    monkeypatch.setattr(create_superuser.getpass, "getpass", lambda prompt="": PASSWORD)

    assert _run(factory, "--username", "root", "--email", "r@x.com") == 0
    assert len(_users(engine)) == 1


@pytest.mark.parametrize(
    ("argv", "stdin"),
    [
        (("--username", "root", "--email", "r@x.com", "--password-stdin"), "short\n"),
        (("--username", "root", "--email", "not-an-email", "--password-stdin"), f"{PASSWORD}\n"),
        (("--username", "root", "--password-stdin"), f"{PASSWORD}\n"),
    ],
    ids=["short-password", "bad-email", "create-without-email"],
)
def test_invalid_input_exits_1_without_writing(db, argv, stdin):
    factory, engine = db

    assert _run(factory, *argv, stdin=stdin) == 1
    assert _users(engine) == []


def test_missing_username_is_a_usage_error(db):
    factory, _ = db
    with pytest.raises(SystemExit) as excinfo:
        _run(factory, "--email", "r@x.com")
    assert excinfo.value.code == 2
