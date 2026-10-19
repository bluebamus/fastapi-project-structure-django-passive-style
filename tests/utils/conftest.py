"""tests/utils 공용 fixture."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.utils.logs import configure_logging

_WATCHED = (
    "",
    "uvicorn",
    "uvicorn.error",
    "uvicorn.access",
    "app.redaction",
    "sqlalchemy.engine",
)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    """dictConfig 는 전역이다 — 이 테스트가 바꾼 로거 상태를 되돌린다."""
    saved = {
        name: (list(lg.handlers), lg.level, lg.propagate, lg.disabled)
        for name in _WATCHED
        for lg in [logging.getLogger(name)]
    }
    configure_logging()
    yield
    for name, (handlers, level, propagate, disabled) in saved.items():
        lg = logging.getLogger(name)
        for h in lg.handlers:
            if h not in handlers:
                h.close()
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
        lg.disabled = disabled
