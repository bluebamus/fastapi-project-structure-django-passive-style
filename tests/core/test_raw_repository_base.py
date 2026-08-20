"""Phase 4 — Raw Base 계약 (requirements RAW-REP-001~005, TEST-001).

여기서 고정하는 것은 셋이다.

* **반환 형태** — ``RowMapping`` / scalar / rowcount. 빈 결과 포함.
* **경계** — commit 하지 않는다. ORM Base 와 상속으로 얽히지 않는다.
* **입력 통제** — ``query_name`` 은 코드 상수여야 하고, SQL 에 값을 보간할 수 없다.

SQLite in-memory 로 실제 실행한다. 방언별 SQL 정확성은 여기서 보증하지 않는다
(ADR-004) — 이 파일이 보는 것은 Base 계약이고, 그건 방언과 무관해야 한다.
"""

from __future__ import annotations

import ast
import io
import logging
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import RowMapping, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db.router import ReadOnlyRoutingError, mark_read_only
from app.core.exception import DatabaseException, DuplicateException
from app.core.repositories.raw_crud_base import RawCRUDBase
from app.core.repositories.raw_repository_base import (
    QUERY_NAME_MAX_LENGTH,
    InvalidQueryNameError,
    RawRepositoryBase,
    validate_query_name,
)
from app.core.repositories.repository_base import BaseRepository

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 로그·응답 어디에도 나타나면 안 되는 값.
SECRET_CANARY = "raw-canary-do-not-log-4c81"

QUERY = "probe.select"

MISSING_TABLE_SQL = "SELECT * FROM table_that_does_not_exist"


class ProbeRawRepository(RawRepositoryBase):
    """도메인 SQL 은 Base 가 아니라 여기 있다 — 그 배치를 이 테스트가 대표한다."""


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as opened:
        await opened.execute(text("CREATE TABLE probe (id INTEGER PRIMARY KEY, name TEXT UNIQUE)"))
        await opened.execute(
            text("INSERT INTO probe (id, name) VALUES (1, :a), (2, :b)"),
            {"a": "alpha", "b": "beta"},
        )
        await opened.commit()
        yield opened
    await engine.dispose()


@pytest.fixture
def repo(session: AsyncSession) -> ProbeRawRepository:
    return ProbeRawRepository(session)


# =============================================================================
# 반환 형태
# =============================================================================
async def test_fetch_one_returns_a_row_mapping(repo: ProbeRawRepository):
    row = await repo.fetch_one(
        text("SELECT id, name FROM probe WHERE name = :name"),
        {"name": "alpha"},
        query_name=QUERY,
    )

    assert isinstance(row, RowMapping), "dict 가 아니라 RowMapping 이어야 컬럼 alias 가 보존된다"
    assert dict(row) == {"id": 1, "name": "alpha"}


async def test_fetch_one_returns_none_when_empty(repo: ProbeRawRepository):
    row = await repo.fetch_one(
        text("SELECT id FROM probe WHERE name = :name"), {"name": "없음"}, query_name=QUERY
    )

    assert row is None


async def test_fetch_all_returns_every_row(repo: ProbeRawRepository):
    rows = await repo.fetch_all(text("SELECT name FROM probe ORDER BY id"), query_name=QUERY)

    assert [row["name"] for row in rows] == ["alpha", "beta"]


async def test_fetch_all_returns_empty_sequence(repo: ProbeRawRepository):
    rows = await repo.fetch_all(
        text("SELECT name FROM probe WHERE id > :id"), {"id": 999}, query_name=QUERY
    )

    assert list(rows) == [], "빈 결과는 None 이 아니라 빈 목록이다 — 호출부가 분기하지 않도록"


async def test_fetch_scalar_returns_first_column(repo: ProbeRawRepository):
    total = await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY)

    assert total == 2


async def test_fetch_scalar_returns_none_when_empty(repo: ProbeRawRepository):
    value = await repo.fetch_scalar(
        text("SELECT name FROM probe WHERE id = :id"), {"id": 999}, query_name=QUERY
    )

    assert value is None


async def test_execute_returns_affected_row_count(repo: ProbeRawRepository):
    affected = await repo.execute(
        text("UPDATE probe SET name = :name WHERE id = :id"),
        {"name": "gamma", "id": 1},
        query_name="probe.rename",
    )

    assert affected == 1


# =============================================================================
# 경계 — commit 하지 않는다
# =============================================================================
async def test_execute_does_not_commit(repo: ProbeRawRepository, session: AsyncSession):
    """Repository 가 commit 하면 View 의 트랜잭션 경계가 의미를 잃는다.

    rollback 후 값이 되돌아오는지로 증명한다 — "commit 을 안 불렀다"가 아니라
    "commit 되지 않았다"를 본다.
    """
    await repo.execute(
        text("INSERT INTO probe (id, name) VALUES (:id, :name)"),
        {"id": 3, "name": "delta"},
        query_name="probe.insert",
    )
    await session.rollback()

    remaining = await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY)
    assert remaining == 2, "execute 가 commit 했다 — rollback 이 되돌리지 못했다"


async def test_fetch_does_not_commit(repo: ProbeRawRepository, session: AsyncSession):
    """조회도 트랜잭션을 닫지 않는다 — 같은 요청의 이후 구문이 새 트랜잭션으로 갈라진다."""
    await repo.execute(
        text("INSERT INTO probe (id, name) VALUES (:id, :name)"),
        {"id": 4, "name": "epsilon"},
        query_name="probe.insert",
    )
    await repo.fetch_all(text("SELECT id FROM probe"), query_name=QUERY)
    await session.rollback()

    assert await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY) == 2


# =============================================================================
# 계층 분리 (AR-003)
# =============================================================================
def test_raw_base_is_not_an_orm_repository():
    """하나의 Base 가 ORM 모델과 Raw row 를 함께 돌려주면 호출부가 타입으로 구분할 수 없다."""
    assert not issubclass(RawRepositoryBase, BaseRepository)
    assert not issubclass(BaseRepository, RawCRUDBase)
    assert issubclass(RawRepositoryBase, RawCRUDBase)


def test_raw_base_owns_no_domain_sql():
    """Base 에 도메인 SQL 이 없다 — 있으면 다음 기능도 여기로 오고 서로 결합된다."""
    for relative in (
        "app/core/repositories/raw_crud_base.py",
        "app/core/repositories/raw_repository_base.py",
    ):
        tree = ast.parse((REPO_ROOT / relative).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
        ]
        assert not calls, f"{relative} 가 SQL 을 소유한다"


# =============================================================================
# query_name — 실행 전에 거부한다
# =============================================================================
@pytest.mark.parametrize(
    "bad",
    [
        "Sales.Daily",  # 대문자
        "sales-report.daily",  # 하이픈
        "sales_report",  # 마디 하나
        "sales.report.daily",  # 마디 셋
        "sales.daily; DROP TABLE probe",  # 주입 시도
        "sales.daily\n",  # 개행 — 로그 한 줄을 쪼갠다
        "",
        "9sales.daily",  # 숫자로 시작
        "x" * (QUERY_NAME_MAX_LENGTH + 1),
    ],
)
def test_invalid_query_name_is_rejected(bad: str):
    with pytest.raises(InvalidQueryNameError):
        validate_query_name(bad)


def test_valid_query_name_passes():
    assert validate_query_name("sales_report.daily_sales") == "sales_report.daily_sales"


async def test_query_name_is_checked_before_the_statement_runs(repo: ProbeRawRepository):
    """검증이 실행 뒤에 있으면 이미 쿼리가 나간 뒤다.

    없는 테이블을 조회한다 — 실행됐다면 ``DatabaseException`` 이 되고, 실행 전에
    막혔다면 ``InvalidQueryNameError`` 다. 어느 쪽인지로 순서를 증명한다.
    """
    with pytest.raises(InvalidQueryNameError):
        await repo.fetch_all(text(MISSING_TABLE_SQL), query_name="사용자 입력")


def _dynamic_query_name_sites(tree: ast.AST) -> list[int]:
    """``query_name=`` 에 상수가 아닌 값을 넘기는 위치의 줄 번호."""
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "query_name":
                continue
            value = keyword.value
            literal = isinstance(value, ast.Constant) and isinstance(value.value, str)
            # 모듈 상수 참조(대문자 이름)도 코드가 소유한 값이므로 허용한다.
            named_constant = isinstance(value, ast.Name) and value.id.isupper()
            if not (literal or named_constant):
                offenders.append(value.lineno)
    return offenders


def test_dynamic_query_name_detector_actually_detects():
    """검사기 자체를 먼저 검증한다 — 조용히 아무것도 못 찾는 검사가 제일 위험하다."""
    assert _dynamic_query_name_sites(ast.parse('f(query_name=request.query_params["q"])'))
    assert _dynamic_query_name_sites(ast.parse('f(query_name="a." + user_input)'))
    assert not _dynamic_query_name_sites(ast.parse('f(query_name="sales.daily")'))
    assert not _dynamic_query_name_sites(ast.parse("f(query_name=QUERY_DAILY_SALES)"))


def test_query_name_is_never_built_from_user_input():
    """``query_name`` 을 넘기는 코드는 전부 문자열 리터럴이나 모듈 상수다.

    요청값으로 만들면 로그 라벨 cardinality 가 무한해지고, 값 자체가 로그에 남는다.
    형식 검증만으로는 "코드가 소유한 상수인가"를 알 수 없어 정적으로 본다.
    """
    offenders: list[str] = []
    for path in sorted(REPO_ROOT.joinpath("app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders += [
            f"{path.relative_to(REPO_ROOT)}:{line}" for line in _dynamic_query_name_sites(tree)
        ]
    assert not offenders, f"query_name 이 코드 상수가 아니다: {offenders}"


# =============================================================================
# 예외 변환과 로그 기밀성
# =============================================================================
async def test_sqlalchemy_error_becomes_an_application_exception(repo: ProbeRawRepository):
    with pytest.raises(DatabaseException):
        await repo.fetch_all(text(MISSING_TABLE_SQL), query_name="probe.missing")


async def test_duplicate_key_becomes_a_conflict(repo: ProbeRawRepository):
    with pytest.raises(DuplicateException):
        await repo.execute(
            text("INSERT INTO probe (id, name) VALUES (:id, :name)"),
            {"id": 9, "name": "alpha"},  # UNIQUE 위반
            query_name="probe.insert",
        )


async def test_converted_error_drops_the_original_cause(repo: ProbeRawRepository):
    """원본을 이어두면 위에서 ``logger.exception`` 한 번에 SQL 과 값이 통째로 찍힌다."""
    await repo.execute(
        text("INSERT INTO probe (id, name) VALUES (:id, :name)"),
        {"id": 10, "name": SECRET_CANARY},
        query_name="probe.insert",
    )

    with pytest.raises(DuplicateException) as caught:
        await repo.execute(
            text("INSERT INTO probe (id, name) VALUES (:id, :name)"),
            {"id": 11, "name": SECRET_CANARY},  # 같은 name → UNIQUE 위반
            query_name="probe.insert",
        )

    converted = caught.value
    assert converted.__cause__ is None
    assert converted.__suppress_context__ is True, "원본이 __context__ 로 남아 traceback 에 나온다"
    assert SECRET_CANARY not in str(converted.detail)
    assert SECRET_CANARY not in converted.message


async def test_logs_carry_query_name_but_not_sql_or_params(repo: ProbeRawRepository):
    """로그에 남는 것은 query_name·소요 시간·성공 여부뿐이다."""
    from app.core.repositories import raw_repository_base as module

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)
    module.logger.addHandler(handler)
    module.logger.setLevel(logging.DEBUG)
    try:
        await repo.fetch_all(
            text("SELECT id FROM probe WHERE name = :name"),
            {"name": SECRET_CANARY},
            query_name="probe.canary_read",
        )
        with pytest.raises(DatabaseException):
            await repo.fetch_all(
                text(MISSING_TABLE_SQL + " WHERE name = :name"),
                {"name": SECRET_CANARY},
                query_name="probe.canary_fail",
            )
    finally:
        module.logger.removeHandler(handler)

    output = buffer.getvalue()
    assert output.strip(), "로그가 아예 안 나갔다 — 검사가 헛통과한다"
    assert "probe.canary_read" in output
    assert "probe.canary_fail" in output
    assert SECRET_CANARY not in output, f"bind 값이 로그에 남았다:\n{output}"
    assert "SELECT" not in output, f"SQL 본문이 로그에 남았다:\n{output}"


# =============================================================================
# named parameter 강제 (RAW-REP-003)
# =============================================================================
async def test_injection_payload_is_bound_not_interpolated(repo: ProbeRawRepository):
    """대표 injection 입력이 값으로만 취급된다."""
    payload = "alpha' OR '1'='1"

    rows = await repo.fetch_all(
        text("SELECT name FROM probe WHERE name = :name"), {"name": payload}, query_name=QUERY
    )

    assert list(rows) == [], "주입 문자열이 조건으로 해석됐다"
    assert await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY) == 2


def _interpolated_text_sites(tree: ast.AST) -> tuple[int, list[int]]:
    """``text()`` 호출 수와, 그중 SQL 을 보간한 위치의 줄 번호."""
    seen = 0
    offenders = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "text"
            and node.args
        ):
            continue
        seen += 1
        first = node.args[0]
        interpolated = (
            isinstance(first, ast.JoinedStr)  # f-string
            or isinstance(first, ast.BinOp)  # "..." + x · "..." % x
            or (
                isinstance(first, ast.Call)
                and isinstance(first.func, ast.Attribute)
                and first.func.attr == "format"
            )
        )
        if interpolated:
            offenders.append(first.lineno)
    return seen, offenders


def test_interpolated_sql_detector_actually_detects():
    """검사기 자체를 먼저 검증한다."""
    assert _interpolated_text_sites(ast.parse('text(f"SELECT * FROM {t}")'))[1]
    assert _interpolated_text_sites(ast.parse('text("SELECT * FROM " + t)'))[1]
    assert _interpolated_text_sites(ast.parse('text("SELECT * FROM %s" % t)'))[1]
    assert _interpolated_text_sites(ast.parse('text("SELECT {}".format(t))'))[1]
    assert not _interpolated_text_sites(ast.parse('text("SELECT * FROM t WHERE a = :a")'))[1]


def test_no_interpolated_sql_in_text_calls():
    """``text()`` 인자에 f-string·``%``·``.format()``·문자열 연결이 없다.

    리뷰로는 놓친다. AST 로 본다. 식별자를 동적으로 골라야 하면 allowlist 에서 고른
    상수로 SQL 을 구성하고, 그때 이 규칙을 ADR 로 다시 연다.
    """
    total = 0
    offenders: list[str] = []
    for path in sorted(REPO_ROOT.joinpath("app").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen, lines = _interpolated_text_sites(tree)
        total += seen
        offenders += [f"{path.relative_to(REPO_ROOT)}:{line}" for line in lines]

    assert total, "app/ 에서 text() 호출을 하나도 못 찾았다 — 검사가 헛통과한다"
    assert not offenders, f"text() 에 보간된 SQL 이 있다: {offenders}"


# =============================================================================
# 읽기 전용 세션 차단 (RAW-REP-007)
# =============================================================================
async def test_execute_is_refused_on_a_read_only_session(session: AsyncSession):
    """라우터가 꺼져 있어도 막힌다 — 설정을 끄면 보안도 꺼지는 상태를 만들지 않는다."""
    mark_read_only(session)
    repo = ProbeRawRepository(session)

    with pytest.raises(ReadOnlyRoutingError):
        await repo.execute(
            text("DELETE FROM probe WHERE id = :id"), {"id": 1}, query_name="probe.delete"
        )

    assert await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY) == 2


async def test_locking_read_is_refused_on_a_read_only_session(session: AsyncSession):
    """``SELECT ... FOR UPDATE`` 는 쓰기다 — replica 에서 잠근 행은 아무것도 보호하지 않는다."""
    mark_read_only(session)
    repo = ProbeRawRepository(session)

    with pytest.raises(ReadOnlyRoutingError):
        await repo.fetch_all(text("SELECT id FROM probe"), query_name=QUERY, for_update=True)


async def test_plain_read_still_works_on_a_read_only_session(session: AsyncSession):
    """과차단도 결함이다 — 읽기 전용 세션에서 읽기는 되어야 한다."""
    mark_read_only(session)
    repo = ProbeRawRepository(session)

    assert await repo.fetch_scalar(text("SELECT COUNT(*) FROM probe"), query_name=QUERY) == 2
