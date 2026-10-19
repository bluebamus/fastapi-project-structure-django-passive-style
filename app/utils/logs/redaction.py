"""로그 비밀값 가리기 — 마스킹 규칙의 정본 (log-redaction-fixes ADR-001).

``SecretRedactor`` 하나가 규칙을 갖고, :func:`install_record_redaction` 이 그것을
``logging`` 의 LogRecord factory 로 건다. factory 는 **어떤 로거·핸들러·포매터로 가든**
레코드가 만들어지는 한 지점이라, 우리 핸들러(console·file·error_file)뿐 아니라 우리가
포매터를 소유하지 않는 경로도 덮는다:

    · ``uvicorn main:app`` CLI — uvicorn 이 자기 dictConfig·포매터로 ``uvicorn.error`` 를 찍는다.
      Starlette 는 500 핸들러가 응답을 만든 뒤에도 예외를 다시 올리므로 uvicorn 이
      ``Exception in ASGI application`` 과 traceback 을 **자기 핸들러로** 남긴다.
    · Celery 워커 — 기본값(``worker_hijack_root_logger``)으로 root 핸들러를 자기 것으로 바꾼다.

가리는 대상: 렌더된 메시지, traceback 본문(``exc_text`` — 여기서 미리 포맷해 고정한다),
``stack_info``. 예외 타입·파일·줄 번호는 값 패턴에 걸리지 않으므로 그대로 남는다.
"""

from __future__ import annotations

import logging
import re
from typing import Any

MASK = "***"

# 키 이름이 이 단어로 **끝나면** 값을 가린다 — ``MYSQL_PASSWORD=…``·``"refresh_token": "…"``·
# ``Authorization: Bearer …``. ``token_type`` 처럼 뒤에 다른 말이 붙으면 걸리지 않는다.
_KEY_WORDS = (
    r"(?:password|passwd|pwd|secret(?:[_-]?key)?|token|api[_-]?key|authorization|credentials?)"
)

_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # DSN·URL 의 userinfo 비밀번호: scheme://user:PASSWORD@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]*:)[^\s@/]+(@)"), rf"\1{MASK}\2"),
    # key=value · key: value · "key": "value" (Authorization 은 scheme 까지 한 덩어리)
    (
        re.compile(
            rf"(?i)(?<![a-z0-9])([\w.-]*{_KEY_WORDS}[\"']?\s*[:=]\s*[\"']?)"
            r"(?:(?:bearer|basic)\s+)?[^\s\"'&,;]+"
        ),
        rf"\1{MASK}",
    ),
    # 키 없이 떠도는 Bearer 토큰
    (re.compile(r"(?i)\b(bearer)\s+[\w.~+/=-]+"), rf"\1 {MASK}"),
    # JWT (header.payload.signature — header 는 항상 eyJ 로 시작한다)
    (re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]*"), MASK),
)


class SecretRedactor:
    """문자열과 LogRecord 에서 비밀값을 ``***`` 로 바꾼다."""

    def __init__(self, rules: tuple[tuple[re.Pattern[str], str], ...] = _RULES) -> None:
        self._rules = rules
        # traceback 을 미리 렌더할 때만 쓴다. 표준 형식이라 어느 포매터의 결과와도 같다.
        self._exc_formatter = logging.Formatter()

    def redact(self, text: str) -> str:
        for pattern, replacement in self._rules:
            text = pattern.sub(replacement, text)
        return text

    def redact_record(self, record: logging.LogRecord) -> None:
        self._redact_message(record)
        if record.exc_info and not record.exc_text:
            # 포매터는 exc_text 가 있으면 다시 포맷하지 않는다 — 가린 본문이 그대로 쓰인다.
            record.exc_text = self.redact(self._exc_formatter.formatException(record.exc_info))
        if record.stack_info:
            record.stack_info = self.redact(record.stack_info)

    def _redact_message(self, record: logging.LogRecord) -> None:
        try:
            rendered = record.getMessage()
        except Exception:
            return  # 형식 오류는 emit 단계에서 logging 이 스스로 보고한다
        clean = self.redact(rendered)
        if clean == rendered:
            return
        # 가능하면 msg·args 구조를 지킨다 — uvicorn AccessFormatter 는 args 튜플을 풀어 쓴다.
        if isinstance(record.args, tuple) and isinstance(record.msg, str):
            msg = self.redact(record.msg)
            args = tuple(self.redact(a) if isinstance(a, str) else a for a in record.args)
            try:
                candidate = msg % args if args else msg
            except (TypeError, ValueError):
                candidate = None
            if candidate is not None and self.redact(candidate) == candidate:
                record.msg, record.args = msg, args
                return
            # 템플릿과 인자에 걸친 일치(예: 접속 줄의 `?token=` + ` HTTP/1.1`)는 인자 하나를 통째로
            # 가려서 깨끗해지면 그것으로 끝낸다 — args 모양을 지켜야 AccessFormatter 줄이 살아남는다.
            for i, arg in enumerate(args):
                if not isinstance(arg, str):
                    continue
                masked = (*args[:i], MASK, *args[i + 1 :])
                try:
                    candidate = msg % masked
                except (TypeError, ValueError):
                    continue
                if self.redact(candidate) == candidate:
                    record.msg, record.args = msg, masked
                    return
        # 비밀값이 템플릿과 인자에 걸쳐 있거나 예외 객체 안에 있으면 렌더 결과로 고정한다.
        record.msg, record.args = clean, None


redactor = SecretRedactor()


def install_record_redaction() -> None:
    """현재 LogRecord factory 를 감싸 모든 레코드를 가린다(여러 번 불러도 한 번만 감싼다)."""
    base = logging.getLogRecordFactory()
    if getattr(base, "_redacting", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = base(*args, **kwargs)
        redactor.redact_record(record)
        return record

    factory._redacting = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)
