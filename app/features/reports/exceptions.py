"""Reports 도메인 예외."""

from enum import StrEnum

from app.core.exception import ValidationException


class ReportsErrorCode(StrEnum):
    """Reports 도메인 에러 코드 (네이밍: REPORTS_{대상}_{원인})."""

    INVALID_DATE_RANGE = "REPORTS_INVALID_DATE_RANGE"


class InvalidDateRangeException(ValidationException):
    """조회 기간이 뒤집혔거나 허용 범위를 넘은 경우."""

    error_code = ReportsErrorCode.INVALID_DATE_RANGE
    message = "조회 기간이 올바르지 않습니다."
