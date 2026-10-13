"""예외 핸들러가 HTTP 의미 헤더를 보존한다 (log-redaction-fixes ADR-003, 리뷰 M-03).

본문은 저장소 오류 봉투(``error_code``·``message``·``detail``) 그대로이고, 예외가 들고 온
헤더(405 ``Allow``·401 ``WWW-Authenticate``·임의 헤더)는 응답에 실린다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core import bootstrap


@pytest.fixture
def client() -> TestClient:
    app = bootstrap.create_app()

    @app.get("/_probe/raise")
    async def _raise(status: int = 401) -> None:
        raise HTTPException(
            status_code=status,
            detail="probe",
            headers={"WWW-Authenticate": "Bearer", "X-Probe": "kept"},
        )

    return TestClient(app, raise_server_exceptions=False)


def _allowed_methods(app: FastAPI, path: str) -> set[str]:
    return {
        method
        for route in app.routes
        if getattr(route, "path", None) == path
        for method in getattr(route, "methods", ())
    }


def test_405_carries_allow_with_the_real_methods(client: TestClient):
    response = client.delete("/health")

    assert response.status_code == 405
    assert "allow" in response.headers
    allowed = {m.strip() for m in response.headers["allow"].split(",")}
    assert allowed == _allowed_methods(client.app, "/health")  # type: ignore[arg-type]
    assert response.json() == {
        "error_code": "HTTP_405",
        "message": "Method Not Allowed",
        "detail": None,
    }


@pytest.mark.parametrize("status", [401, 418])
def test_http_exception_headers_reach_the_response(client: TestClient, status: int):
    response = client.get("/_probe/raise", params={"status": status})

    assert response.status_code == status
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.headers["x-probe"] == "kept"
    assert response.json() == {"error_code": f"HTTP_{status}", "message": "probe", "detail": None}


def test_404_without_headers_keeps_the_envelope(client: TestClient):
    response = client.get("/_probe/none")

    assert response.status_code == 404
    assert response.json() == {"error_code": "HTTP_404", "message": "Not Found", "detail": None}
