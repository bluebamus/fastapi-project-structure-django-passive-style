"""DB 예외 → 애플리케이션 예외 안전 변환기 (development-plan Phase 3 · ledger F-015).

SQLAlchemy 예외의 ``str()`` 에는 **실행된 SQL 과 바인딩된 값**이 들어 있다. 값에는
비밀번호 해시·토큰·개인정보가 섞이고, DSN 이 통째로 들어오는 경우도 있다. 그런데
그 예외는 두 방향으로 샌다.

1. **응답** — ``detail`` 에 실어 보내면 API 클라이언트가 그대로 받는다(F-011 에서 차단).
2. **로그** — ``raise ... from e`` 로 원인을 이어 두면, 위에서 누가 ``logger.exception``
   을 호출하는 순간 traceback 에 원본 메시지가 통째로 찍힌다. 로거 이름이 ``app.*``
   이라 ``SqlNoiseFilter`` 도 통과한다(F-015).

그래서 **경계에서 한 번** 변환한다. 여기서 안전한 것만 골라 로그에 남기고, 원본은
``raise ... from None`` 으로 끊는다. 원본을 이어 붙이지 않는 것이 핵심이다 — 이어
두면 언젠가 누군가 traceback 을 찍고, 그 시점은 대개 장애 중이라 아무도 못 본다.

무엇이 "안전한가":

* 예외 클래스 이름 (``IntegrityError``, ``OperationalError`` …)
* 드라이버 에러 코드 (MySQL 1062 = 중복 키, 1452 = FK 위반 …)
* 어떤 모델·어떤 연산이었는지

이 셋이면 로그에서 원인을 좁히기에 충분하다. 값이 필요하면 요청 로그와 대조한다.

.. note::
   드라이버 메시지 본문(``e.orig.args[1]``)은 **의도적으로 버린다**. 거기에 값이 있다.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.core.exception import AppException, DatabaseException, DuplicateException
from app.utils.logs import get_logger

logger = get_logger("db.errors")

#: MySQL 중복 키 에러 코드.
MYSQL_DUPLICATE_ENTRY = 1062


def driver_error_code(exc: BaseException) -> int | None:
    """드라이버가 준 숫자 에러 코드. 없으면 ``None``.

    MySQL 이면 1062(중복 키)·1452(FK 위반) 같은 값이 나온다. 코드만 남기고 메시지는
    버린다 — 메시지에 값이 들어 있다.
    """
    orig = getattr(exc, "orig", None)
    args = getattr(orig, "args", None)
    if args and isinstance(args[0], int):
        return args[0]
    return None


def convert_db_error(
    exc: SQLAlchemyError,
    *,
    operation: str,
    model: str,
    **detail: Any,
) -> AppException:
    """DB 예외를 안전한 애플리케이션 예외로 바꾸고, 안전한 것만 로그에 남긴다.

    Args:
        exc: 원본 SQLAlchemy 예외.
        operation: 무슨 일을 하다 났는지 (``CREATE``·``UPDATE`` …). 로그용.
        model: 대상 모델 이름.
        **detail: 응답에 실어도 되는 추가 정보(``id`` 등). **값이 아니라 식별자만**.

    Returns:
        호출부가 ``raise ... from None`` 으로 던질 예외.

    사용법::

        except SQLAlchemyError as exc:
            raise convert_db_error(exc, operation="CREATE", model="User") from None

    ``from None`` 이 빠지면 원본이 ``__context__`` 로 남아 traceback 에 다시 나타난다.
    :func:`tests.core.test_db_error_conversion` 이 그 누락을 잡는다.
    """
    code = driver_error_code(exc)
    logger.error(
        "[%s] %s (model=%s, driver_code=%s)",
        operation,
        type(exc).__name__,
        model,
        code,
    )

    payload: dict[str, Any] = {"model": model, **detail}

    if isinstance(exc, IntegrityError):
        # 중복 키와 FK/NOT NULL 위반은 사용자에게 다른 의미다(409 vs 500). 코드로만
        # 가른다 — 메시지를 파싱하면 그 순간 값이 딸려 온다.
        #
        # 코드를 주지 않는 방언(SQLite)에서는 **중복으로 본다**. 이 프로젝트의 단위
        # 테스트가 SQLite 이고 거기서 나는 IntegrityError 는 사실상 unique 위반이다.
        # 정확한 구분은 MySQL 통합 테스트가 담당한다(ADR-004: SQLite 는 방언 정확성의
        # 근거가 아니다).
        if code is None or code == MYSQL_DUPLICATE_ENTRY:
            return DuplicateException(
                message="이미 존재하는 데이터입니다.",
                detail=payload,
            )
        return DatabaseException(
            message="데이터 제약 조건을 만족하지 않습니다.",
            detail=payload,
        )

    return DatabaseException(
        message="데이터베이스 처리 중 오류가 발생했습니다.",
        detail=payload,
    )
