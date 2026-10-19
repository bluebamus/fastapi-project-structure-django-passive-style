"""DB 오류·로그에 바인드 값이 실리지 않는다 — ``hide_parameters=True`` (security-ops-hardening ADR-001).

고유 제약 위반 하나로 ``IntegrityError`` 의 메시지에 INSERT 의 값(이메일·비밀번호 해시)이 그대로
실린다. 그 예외는 traceback·``logger.exception`` 으로 로그 수집기까지 간다. 엔진 옵션 정본
``ENGINE_SAFETY_OPTIONS`` 가 모든 엔진 생성 지점에 들어갔는지(계약), 실제로 값이 빠지는지(동작),
로그 파이프라인 출력에도 없는지를 본다.
"""

from __future__ import annotations

import ast
import io
import logging
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import session as db_session
from app.core.db.session import ENGINE_SAFETY_OPTIONS
from app.utils.logs import configure_logging
from app.utils.logs.formatters import TzFormatter

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_FACTORIES = {"create_async_engine", "create_engine", "engine_from_config"}

_metadata = sa.MetaData()
_accounts = sa.Table(
    "hide_probe_accounts",
    _metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("email", sa.String(200), nullable=False, unique=True),
    sa.Column("hashed_password", sa.String(200), nullable=False),
)


async def _integrity_error() -> tuple[IntegrityError, str, str]:
    """앱 엔진과 같은 옵션의 SQLite 엔진으로 고유 제약 위반을 일으킨다."""
    email = f"probe-{uuid4().hex}@leak.test"
    hashed = f"argon2-probe-{uuid4().hex}"
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", **ENGINE_SAFETY_OPTIONS)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(_metadata.create_all)
            row = {"email": email, "hashed_password": hashed}
            await conn.execute(_accounts.insert(), row)
            with pytest.raises(IntegrityError) as caught:
                await conn.execute(_accounts.insert(), row)
    finally:
        await engine.dispose()
    return caught.value, email, hashed


async def test_integrity_error_message_keeps_the_sql_but_not_the_values():
    error, email, hashed = await _integrity_error()

    text = str(error)
    assert email not in text and hashed not in text, text
    assert "INSERT INTO hide_probe_accounts" in text, "SQL 문은 진단을 위해 남아야 한다"
    assert "hide_parameters" in text


async def test_logger_exception_output_has_no_bound_values():
    configure_logging()
    error, email, hashed = await _integrity_error()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TzFormatter("{levelname} {message}"))
    logger = logging.getLogger("tests.hide_parameters")
    logger.addHandler(handler)
    try:
        try:
            raise error
        except IntegrityError:
            logger.exception("DB 쓰기 실패")
    finally:
        logger.removeHandler(handler)

    output = stream.getvalue()
    assert "DB 쓰기 실패" in output and "IntegrityError" in output
    assert email not in output and hashed not in output, output


def test_every_application_engine_hides_parameters():
    read_engine = db_session._create_read_engine(make_url("mysql+aiomysql://u:p@replica/db"))
    engines = [db_session.engine, db_session.background_engine, read_engine]
    engines += db_session.read_engines

    assert all(e.sync_engine.hide_parameters for e in engines), [
        e.sync_engine.url.host for e in engines if not e.sync_engine.hide_parameters
    ]


def _engine_calls_without_safety_options(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    missing: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name not in ENGINE_FACTORIES:
            continue
        spread = [
            kw.value.id for kw in node.keywords if kw.arg is None and isinstance(kw.value, ast.Name)
        ]
        if "ENGINE_SAFETY_OPTIONS" not in spread:
            missing.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno} {name}")
    return missing


def test_every_engine_creation_site_spreads_the_safety_options():
    """새 엔진 생성 지점이 옵션 정본을 빠뜨리면 여기서 떨어진다(테스트 코드는 대상 밖)."""
    sources = [
        path
        for root in ("app", "migrations", "scripts")
        for path in (REPO_ROOT / root).rglob("*.py")
        if "tests" not in path.parts
    ]
    sources.append(REPO_ROOT / "config.py")

    missing = [m for path in sources for m in _engine_calls_without_safety_options(path)]

    assert not missing, missing
    assert ENGINE_SAFETY_OPTIONS["hide_parameters"] is True
