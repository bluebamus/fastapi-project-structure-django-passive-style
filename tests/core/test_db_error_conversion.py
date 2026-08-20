"""Phase 3a — DB 예외 안전 변환기와 F-015 (development-plan Phase 3).

여기서 닫는 것은 **로그 경유 유출**이다. Round 1 에서 `SqlNoiseFilter` 를 붙였지만
그 필터는 *로거 이름*으로 거른다. 앱 로거(`app.*`)가 DB 예외를 traceback 과 함께
남기면 그 줄은 필터를 그대로 통과하고, traceback 안에는 실행된 SQL 과 바인딩된 값이
들어 있다.

그래서 경계에서 원본을 끊는다(`raise ... from None`). 이 파일은 그 차단이 실제로
동작하는지를 **카나리아 값**으로 확인한다 — 계약 문장이 아니라 실제 출력에서.
"""

from __future__ import annotations

import ast
import io
import logging
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.db.errors import MYSQL_DUPLICATE_ENTRY, convert_db_error, driver_error_code
from app.core.exception import DatabaseException, DuplicateException

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 실제 유출을 흉내내는 값. DB 예외 메시지에 넣고 어디에도 안 나타나는지 본다.
SECRET_CANARY = "s3cr3t-canary-do-not-log-9f2b"


def _integrity_error(code: int | None = MYSQL_DUPLICATE_ENTRY) -> IntegrityError:
    """실제와 같은 모양의 IntegrityError — SQL·파라미터·드라이버 메시지를 모두 담는다."""
    orig: Exception
    if code is None:
        orig = Exception(f"UNIQUE constraint failed: users.token ({SECRET_CANARY})")
    else:
        orig = Exception(code, f"Duplicate entry '{SECRET_CANARY}' for key 'users.token'")
    return IntegrityError(
        statement="INSERT INTO users (token) VALUES (%(token)s)",
        params={"token": SECRET_CANARY},
        orig=orig,
    )


# =============================================================================
# 변환 결과
# =============================================================================
def test_mysql_duplicate_becomes_conflict():
    """중복 키는 409 다 — 클라이언트가 고칠 수 있는 오류."""
    converted = convert_db_error(_integrity_error(), operation="CREATE", model="User")

    assert isinstance(converted, DuplicateException)
    assert converted.detail == {"model": "User"}


def test_other_integrity_violation_is_not_a_duplicate():
    """FK·NOT NULL 위반을 "이미 존재합니다"로 답하면 호출자가 잘못된 조치를 한다."""
    converted = convert_db_error(_integrity_error(code=1452), operation="CREATE", model="Reply")

    assert isinstance(converted, DatabaseException)
    assert not isinstance(converted, DuplicateException)


def test_dialect_without_error_code_falls_back_to_duplicate():
    """SQLite 는 코드를 주지 않는다 — 기존 동작(409)을 유지한다.

    정확한 구분은 MySQL 통합 테스트가 맡는다(ADR-004).
    """
    converted = convert_db_error(_integrity_error(code=None), operation="CREATE", model="User")

    assert isinstance(converted, DuplicateException)


def test_non_integrity_errors_become_database_errors():
    error = OperationalError(
        statement="SELECT 1", params={}, orig=Exception(2003, f"host={SECRET_CANARY}")
    )

    converted = convert_db_error(error, operation="READ", model="User")

    assert isinstance(converted, DatabaseException)


def test_driver_error_code_extraction():
    assert driver_error_code(_integrity_error()) == MYSQL_DUPLICATE_ENTRY
    assert driver_error_code(_integrity_error(code=None)) is None
    assert driver_error_code(Exception("코드 없음")) is None


# =============================================================================
# F-015 — 카나리아가 응답에도 로그에도 나타나지 않는다
# =============================================================================
def test_converted_exception_carries_no_secret_in_its_payload():
    """응답으로 나가는 detail·message 에 원본이 없다."""
    converted = convert_db_error(_integrity_error(), operation="CREATE", model="User", id="user-1")

    assert SECRET_CANARY not in str(converted.detail)
    assert SECRET_CANARY not in converted.message


def test_converted_exception_drops_the_original_cause():
    """원본을 ``__cause__``/``__context__`` 로 이어두지 않는다.

    이어두면 위에서 누가 ``logger.exception`` 을 부르는 순간 traceback 에 원본이
    통째로 찍힌다 — 그게 F-015 였다.
    """
    try:
        try:
            raise _integrity_error()
        except IntegrityError as exc:
            raise convert_db_error(exc, operation="CREATE", model="User") from None
    except DuplicateException as converted:
        assert converted.__cause__ is None
        assert (
            converted.__suppress_context__ is True
        ), "원본이 __context__ 로 남아 traceback 에 다시 나타난다"


def test_converter_logs_only_safe_fields():
    """변환기가 남기는 로그에 카나리아가 없고, 원인을 좁힐 단서는 있다."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)

    # 이름을 추측하지 않는다 — 모듈이 쓰는 그 logger 객체를 그대로 붙인다.
    from app.core.db import errors as errors_module

    logger = errors_module.logger
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        convert_db_error(_integrity_error(), operation="CREATE", model="User")
    finally:
        logger.removeHandler(handler)

    output = buffer.getvalue()
    assert output.strip(), "로그가 아예 안 나갔다 — 검사가 헛통과한다"
    assert SECRET_CANARY not in output, f"변환기 로그에 secret 이 남았다: {output}"
    assert "IntegrityError" in output
    assert str(MYSQL_DUPLICATE_ENTRY) in output
    assert "User" in output


def test_traceback_of_converted_exception_has_no_secret():
    """최종 formatter 출력까지 확인한다 — F-015 의 실제 완료 조건."""
    from app.utils.logs import LOG_FORMAT
    from app.utils.logs.filters import ContextFilter, SqlNoiseFilter
    from app.utils.logs.formatters import TzFormatter

    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setLevel(logging.DEBUG)
    handler.addFilter(SqlNoiseFilter(allow_sql_echo=False))
    handler.addFilter(ContextFilter())
    handler.setFormatter(TzFormatter(LOG_FORMAT))

    logger = logging.getLogger("app.features.probe")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    try:
        try:
            try:
                raise _integrity_error()
            except IntegrityError as exc:
                raise convert_db_error(exc, operation="CREATE", model="User") from None
        except DuplicateException:
            # 500 핸들러가 하던 것과 같은 호출.
            logger.exception("[UnhandledException] %s", "DuplicateException")
    finally:
        logger.removeHandler(handler)
        logger.propagate = True

    output = buffer.getvalue()
    assert "UnhandledException" in output, "로그가 안 나갔다 — 검사가 헛통과한다"
    assert SECRET_CANARY not in output, (
        "traceback 에 secret 이 남았다 — F-015 가 닫히지 않았다:\n"
        + "\n".join(line for line in output.splitlines() if SECRET_CANARY in line)
    )


# =============================================================================
# 구조 — 변환기를 우회하는 경로가 없어야 한다
# =============================================================================
def test_repository_and_commit_paths_use_the_converter():
    """Repository 와 commit 경로가 원본 예외를 그대로 올리지 않는다."""
    for relative in (
        "app/core/repositories/repository_base.py",
        "app/core/services/services_base.py",
    ):
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            handled = ast.unparse(node.type) if node.type else ""
            if "SQLAlchemyError" not in handled and "IntegrityError" not in handled:
                continue
            body = ast.unparse(node)
            assert (
                "convert_db_error" in body
            ), f"{relative} 의 DB 예외 처리가 변환기를 거치지 않는다:\n{body[:200]}"
            assert (
                "from None" in body
            ), f"{relative} 가 원본을 이어붙인다 — traceback 으로 샌다:\n{body[:200]}"


def test_unhandled_db_exception_is_logged_without_traceback():
    """변환기를 거치지 않은 DB 예외가 올라와도 traceback 을 찍지 않는다.

    정상 경로는 경계에서 막지만, 아직 변환기를 거치지 않는 경로(Raw SQL 등)가
    생길 수 있다. 마지막 방어선에서도 원본이 출력되지 않아야 한다.
    """
    source = (REPO_ROOT / "app" / "core" / "bootstrap.py").read_text(encoding="utf-8")

    assert (
        "isinstance(exc, SQLAlchemyError)" in source
    ), "500 핸들러가 DB 예외를 구분하지 않는다 — logger.exception 이 traceback 을 찍는다"
    assert "driver_error_code" in source, "원인을 좁힐 단서(드라이버 코드)를 남기지 않는다"


@pytest.mark.parametrize("relative", ["app/core/repositories/repository_base.py"])
def test_no_raw_db_message_reaches_the_response(relative: str):
    """응답 payload 로 원본 DB 메시지가 나가는 경로가 없다 (F-011 회귀 방지)."""
    source = (REPO_ROOT / relative).read_text(encoding="utf-8")
    code_lines = [line for line in source.splitlines() if not line.lstrip().startswith("#")]
    offenders = [line.strip() for line in code_lines if "str(e)" in line or "str(e.orig)" in line]
    assert not offenders, f"{relative} 에 원본 DB 메시지 노출 경로가 있다: {offenders}"
