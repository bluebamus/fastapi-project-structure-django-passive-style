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


def _run(
    factory, *argv: str, stdin: str = f"{PASSWORD}\n", revoked: list[str] | None = None
) -> int:
    """관리 세션 폐기는 기록만 한다 — 실제 Redis 에 붙지 않는다."""
    calls = revoked if revoked is not None else []

    async def record(user_id: str) -> None:
        calls.append(user_id)

    return create_superuser.main(
        list(argv),
        session_factory=factory,
        stdin=io.StringIO(stdin),
        revoke_sessions=record,
    )


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

    revoked: list[str] = []
    code = _run(factory, "--username", "alice", stdin="", revoked=revoked)

    assert code == 0
    [(_, _, is_superuser, hashed)] = _users(engine)
    assert (is_superuser, hashed) == (True, "keep-me")
    assert revoked == [], "비밀번호를 바꾸지 않았는데 관리 세션을 지웠다"


def test_set_password_rehashes_when_promoting(db):
    factory, engine = db
    _run(factory, "--username", "bob", "--email", "b@x.com", "--password-stdin")

    revoked: list[str] = []
    code = _run(
        factory,
        "--username",
        "bob",
        "--set-password",
        "--password-stdin",
        stdin="new-pass-456\n",
        revoked=revoked,
    )

    assert code == 0
    [(_, _, _, hashed)] = _users(engine)
    assert get_password_hasher().verify_and_update("new-pass-456", hashed)[0] is True
    with engine.connect() as connection:
        bob_id = connection.execute(sa.text("SELECT id FROM users WHERE username='bob'")).scalar()
    assert revoked == [bob_id], "비밀번호를 바꿨는데 그 사용자의 관리 세션을 지우지 않았다"


async def test_production_revoker_deletes_that_users_sessions_in_redis(monkeypatch):
    """운영 조립(``revoke_sessions_in_redis``)이 설정의 Redis 에서 그 사용자의 관리 세션·refresh 만 지운다."""
    from fakeredis import FakeServer
    from fakeredis.aioredis import FakeRedis

    from app.core.security.admin_session import SESSION_USER_KEY, default_admin_session_store
    from app.core.security.dependencies import get_refresh_token_store

    server = FakeServer()

    class _Factory:
        @staticmethod
        def from_url(url: str) -> FakeRedis:
            return FakeRedis(server=server)

    monkeypatch.setattr("redis.asyncio.Redis", _Factory)
    store = default_admin_session_store(FakeRedis(server=server))
    mine = await store.create({SESSION_USER_KEY: "u-carol"})
    other = await store.create({SESSION_USER_KEY: "u-other"})
    refresh = get_refresh_token_store(FakeRedis(server=server))
    await refresh.register("jti-c", "u-carol", "fam-c")
    await refresh.register("jti-o", "u-other", "fam-o")

    await create_superuser.revoke_sessions_in_redis("u-carol")

    assert await store.load(mine) is None
    assert await store.load(other) is not None
    assert await refresh.is_family_revoked("fam-c")
    assert not await refresh.is_family_revoked("fam-o")


def test_cli_set_password_revokes_refresh_and_admin_sessions(db, monkeypatch):
    """계약(integration-e2e ADR-012 결정 4): ``--set-password`` 는 API 비밀번호 변경과 같게 그 사용자의 refresh family 와
    관리 세션을 지운다 — ``main()`` 의 기본 조립(``revoke_sessions_in_redis``)으로, 다른 사용자는 건드리지 않는다.
    """
    import asyncio

    from fakeredis import FakeServer
    from fakeredis.aioredis import FakeRedis

    from app.core.security.admin_session import SESSION_USER_KEY, default_admin_session_store
    from app.core.security.dependencies import get_refresh_token_store

    factory, engine = db
    _run(factory, "--username", "erin", "--email", "e@x.com", "--password-stdin")
    with engine.connect() as connection:
        erin = connection.execute(sa.text("SELECT id FROM users WHERE username='erin'")).scalar()

    server = FakeServer()

    class _Factory:
        @staticmethod
        def from_url(url: str) -> FakeRedis:
            return FakeRedis(server=server)

    monkeypatch.setattr("redis.asyncio.Redis", _Factory)

    async def seed() -> tuple[str, str]:
        store = default_admin_session_store(FakeRedis(server=server))
        refresh = get_refresh_token_store(FakeRedis(server=server))
        await refresh.register("jti-e", erin, "fam-e")
        await refresh.register("jti-o", "u-other", "fam-o")
        return (
            await store.create({SESSION_USER_KEY: erin}),
            await store.create({SESSION_USER_KEY: "u-other"}),
        )

    mine, other = asyncio.run(seed())

    code = create_superuser.main(
        ["--username", "erin", "--set-password", "--password-stdin"],
        session_factory=factory,
        stdin=io.StringIO("new-pass-789\n"),
    )

    async def state() -> tuple[bool, bool, bool, bool]:
        store = default_admin_session_store(FakeRedis(server=server))
        refresh = get_refresh_token_store(FakeRedis(server=server))
        return (
            await store.load(mine) is None,
            await store.load(other) is None,
            await refresh.is_family_revoked("fam-e"),
            await refresh.is_family_revoked("fam-o"),
        )

    assert code == 0
    assert asyncio.run(state()) == (True, False, True, False)


def test_redis_failure_after_password_change_exits_1(db, capsys):
    from redis.exceptions import ConnectionError as RedisConnectionError

    factory, _ = db
    _run(factory, "--username", "dave", "--email", "d@x.com", "--password-stdin")

    async def down(user_id: str) -> None:
        raise RedisConnectionError("down")

    code = create_superuser.main(
        ["--username", "dave", "--set-password", "--password-stdin"],
        session_factory=factory,
        stdin=io.StringIO("new-pass-456\n"),
        revoke_sessions=down,
    )

    assert code == 1
    assert "세션을 지우지 못했습니다" in capsys.readouterr().err
    # 순서 계약: 비밀번호는 커밋된 뒤 폐기한다 — 폐기가 실패해도 새 비밀번호는 남고, 종료 코드 1 과 메시지가
    # "다시 실행하라" 를 알린다(다시 실행하면 같은 비밀번호로 폐기만 다시 한다).
    [(_, _, _, hashed)] = _users(db[1])
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
