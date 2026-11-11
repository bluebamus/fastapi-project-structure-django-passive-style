"""테스트 전역 설정.

Python 3.12 에서 ``sqlite3`` 의 기본 ``date``/``datetime`` 어댑터가 폐기됐다.
Raw ``text()`` 는 타입 정보가 없어 bind 값이 드라이버로 **그대로** 가므로
(`app/features/reports/repositories/sales_report_repository.py` 의 기간 파라미터),
SQLite 로 도는 테스트에서 그 폐기 경고가 난다. 서드파티 버그가 아니라 우리가
어댑터를 등록하지 않은 것이므로, 억제하지 않고 **명시 등록**으로 없앤다.

값은 폐기된 기본 어댑터와 동일한 문자열을 만든다 — 저장 형식이 달라지면
``DATE(...)`` 같은 SQL 함수와 문자열 비교가 조용히 틀어진다.
"""

import sqlite3
from datetime import date, datetime

import pytest

sqlite3.register_adapter(date, date.isoformat)
sqlite3.register_adapter(datetime, lambda value: value.isoformat(sep=" "))


@pytest.fixture
def restore_config():
    """``importlib.reload(config)`` 를 하는 테스트가 끝나면 원래 설정 **객체**로 되돌린다.

    reload 는 같은 모듈 dict 에 새 설정 객체를 채운다. 다시 reload 해서 "원래 환경"으로
    돌려도 객체는 또 새것이라, 수집 시점에 ``from config import db_settings`` 로 잡아 둔
    객체와 ``migrations/env.py`` 가 실행 시점에 읽는 ``config.db_settings`` 가 갈라진다 —
    그 객체를 patch 한 테스트는 실행 순서에 따라 alembic 을 엉뚱한 DB 로 보낸다.
    스냅샷을 통째로 되돌리면 어떤 순서로 돌아도 모두 같은 객체를 본다.
    """
    import config as config_module

    snapshot = dict(vars(config_module))
    yield config_module
    vars(config_module).clear()
    vars(config_module).update(snapshot)
