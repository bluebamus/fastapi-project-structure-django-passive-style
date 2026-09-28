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

sqlite3.register_adapter(date, date.isoformat)
sqlite3.register_adapter(datetime, lambda value: value.isoformat(sep=" "))
