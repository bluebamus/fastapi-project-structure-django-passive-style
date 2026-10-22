"""처리기가 없는 예외(버그) → 500, 기록 한 번, keep-alive 유지 (integration-e2e ADR-012 결정 2).

Starlette ``ServerErrorMiddleware`` 는 ``Exception`` 처리기로 응답한 뒤 예외를 **다시 던진다** — uvicorn 이
``Exception in ASGI application`` 으로 한 번 더 기록하고 연결을 닫는다. 사용자 미들웨어 중 가장 바깥에서
예외를 받아 같은 처리기로 응답을 끝내면 세 가지가 함께 성립한다: 로그 1번, 연결 유지, 응답 불변.
"""

from __future__ import annotations

import http.client
import logging
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.core import bootstrap

BODY = {
    "error_code": "INTERNAL_SERVER_ERROR",
    "message": "내부 서버 오류가 발생했습니다.",
    "detail": None,
}


@pytest.fixture(autouse=True)
def _production_mode(monkeypatch):
    """pytest 환경은 ``DEBUG=true``(pyproject env) — 운영 동작을 보려면 끈다. 미들웨어는 요청 시점에 읽는다."""
    monkeypatch.setattr(bootstrap.app_settings, "DEBUG", False)


def _app_with_bug():
    app = bootstrap.create_app()

    @app.get("/_probe/bug", include_in_schema=False)
    async def _bug() -> None:
        raise RuntimeError("버그(모의)")

    @app.get("/_probe/ok", include_in_schema=False)
    async def _ok() -> dict[str, bool]:
        return {"ok": True}

    return app


def test_bug_is_answered_inside_the_app_and_not_raised_again():
    """``raise_server_exceptions=True`` 여도 예외가 테스트로 올라오지 않는다 — 앱 안에서 끝났다."""
    response = TestClient(_app_with_bug()).get("/_probe/bug")  # lifespan 없이(DB·Redis 불필요)

    assert response.status_code == 500
    assert response.json() == BODY


def test_the_catcher_is_the_outermost_user_middleware():
    """다른 사용자 미들웨어(CORS·UserInfo) 안에서 난 예외도 받으려면 가장 바깥이어야 한다."""
    outermost = bootstrap.create_app().user_middleware[0]

    assert outermost.kwargs.get("dispatch") is not None
    assert outermost.kwargs["dispatch"].__name__ == "answer_unhandled_exception"


def test_bug_inside_another_middleware_is_answered_too(monkeypatch):
    from app.core.middlewares import user_info_middleware

    async def broken(self, request, call_next):
        raise RuntimeError("미들웨어 버그(모의)")

    monkeypatch.setattr(user_info_middleware.UserInfoMiddleware, "dispatch", broken)
    response = TestClient(bootstrap.create_app()).get("/health")

    assert response.status_code == 500
    assert response.json() == BODY


def test_debug_keeps_raising(monkeypatch):
    """``DEBUG=true`` 는 지금처럼 다시 던진다(개발 중 서버 콘솔·테스트에 예외가 보이게)."""
    app = _app_with_bug()
    monkeypatch.setattr(bootstrap.app_settings, "DEBUG", True)

    with pytest.raises(RuntimeError, match="모의"):
        TestClient(app).get("/_probe/bug")


def test_real_uvicorn_logs_once_and_keeps_the_connection(caplog):
    """실제 uvicorn — 앱 기록 1건, ``Exception in ASGI application`` 0건, 같은 연결의 다음 요청 성공."""
    app = _app_with_bug()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=0, lifespan="off", log_config=None)
    )
    thread = threading.Thread(target=server.run, daemon=True)
    logging.getLogger().addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            thread.start()
            deadline = time.monotonic() + 10
            while not server.started and time.monotonic() < deadline:
                time.sleep(0.02)
            assert server.started, "uvicorn 이 뜨지 않았다"
            port = server.servers[0].sockets[0].getsockname()[1]

            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
            try:
                conn.request("GET", "/_probe/bug")
                first = conn.getresponse()
                first.read()
                conn.request("GET", "/_probe/ok")  # 같은 연결 — 닫혔으면 여기서 실패한다
                second = conn.getresponse()
                second.read()
            finally:
                conn.close()
            time.sleep(0.2)
    finally:
        server.should_exit = True
        thread.join(10)
        logging.getLogger().removeHandler(caplog.handler)

    messages = [record.getMessage() for record in caplog.records]
    assert (first.status, first.will_close) == (500, False)
    assert second.status == 200
    assert sum("[UnhandledException]" in m for m in messages) == 1, messages
    assert not [m for m in messages if "Exception in ASGI application" in m], messages
