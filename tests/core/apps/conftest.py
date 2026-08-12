"""Registry 계약 테스트 공통 fixture.

전역 registry 를 쓰지 않는다 — 테스트마다 격리된 ``Apps()`` 를 만든다(NFR-05).
fixture 앱은 import 부수효과로 이벤트를 남기므로, 매 테스트 전에 이벤트 로그를
비우고 fixture 모듈을 ``sys.modules`` 에서 걷어내 "이번 population 이 무엇을
import 했는가" 만 관찰되게 한다.
"""

import sys
from collections.abc import Iterator

import pytest

from app.core.apps import Apps
from tests.core.apps._fixtures import eventlog

FIXTURE_PKG = "tests.core.apps._fixtures"


def _purge_fixture_modules() -> None:
    """fixture 앱 모듈만 sys.modules 에서 제거한다.

    ``eventlog`` 는 이벤트 리스트 객체 자체를 들고 있어 다시 import 되면 안 되므로 남긴다.
    """
    keep = {FIXTURE_PKG, f"{FIXTURE_PKG}.eventlog"}
    for name in [n for n in sys.modules if n.startswith(f"{FIXTURE_PKG}.")]:
        if name not in keep:
            del sys.modules[name]


@pytest.fixture(autouse=True)
def _clean_fixture_state() -> Iterator[None]:
    _purge_fixture_modules()
    eventlog.reset()
    yield
    _purge_fixture_modules()
    eventlog.reset()


@pytest.fixture
def registry() -> Apps:
    """테스트 격리용 독립 registry 인스턴스."""
    return Apps()


@pytest.fixture
def events() -> list[str]:
    """population 단계 이벤트 로그(리스트 객체 자체를 공유한다)."""
    return eventlog.EVENTS
