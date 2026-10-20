"""live server 하네스 자체의 계약 — 요청이 쌓여도 서버가 멈추지 않는다 (integration-e2e F-002).

서버 출력을 ``stdout=PIPE`` 로 받고 아무도 읽지 않으면, 파이프 버퍼가 차는 순간 서버가 로그 한 줄을 쓰다
멈춘다. Windows 는 버퍼가 작아 접속 로그 몇 줄 만에 막힌다(실측: 9번째 요청에서 ReadTimeout) — 그 뒤의
브라우저 테스트는 전부 ``goto`` 시간 초과로 보여 원인이 가려진다.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.browser


def test_live_server_keeps_serving_after_many_logged_requests(live_server: str):
    with httpx.Client(base_url=live_server, timeout=10) as client:
        statuses = {client.get("/health").status_code for _ in range(300)}
    assert statuses == {200}
