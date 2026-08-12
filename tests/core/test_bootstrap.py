"""``create_app()`` 조립과 lifespan 계약 (FR-07·BC-03·NFR-05).

lifespan 은 지금까지 어떤 테스트도 실행하지 않던 구간이다 — ``TestClient`` 를 context
manager 로 쓰지 않으면 startup/shutdown 이 돌지 않기 때문이다. 그런데 여기 있는 두
분기(DEBUG 여부)와 종료 시 drain 순서가 배포에서 가장 먼저 문제를 일으키는 코드다.

DB 호출은 대체한다 — 검증 대상은 "테이블을 만드는가" 가 아니라 **조립부가 어떤 순서로
무엇을 부르는가** 이고, 실제 테이블 생성은 migration 테스트가 따로 본다.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.core import bootstrap
from app.core.apps import Apps
from config import INSTALLED_APPS


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """lifespan 이 부르는 외부 호출을 순서대로 기록한다."""
    recorded: list[str] = []

    async def fake_create_tables() -> None:
        recorded.append("create_db_tables")

    async def fake_dispose() -> None:
        recorded.append("dispose_engine")

    class _Tasks:
        async def drain(self) -> None:
            recorded.append("drain")

    monkeypatch.setattr(bootstrap, "create_db_tables", fake_create_tables)
    monkeypatch.setattr(bootstrap, "dispose_engine", fake_dispose)
    monkeypatch.setattr(bootstrap, "access_log_tasks", _Tasks())
    return recorded


async def _run_lifespan(app: FastAPI) -> None:
    async with bootstrap.lifespan(app):
        pass


async def test_lifespan_creates_tables_in_debug(calls: list[str], monkeypatch):
    """DEBUG=True 면 테이블을 만들고, 종료 시 drain 후 엔진을 정리한다."""
    monkeypatch.setattr(bootstrap.app_settings, "DEBUG", True)

    await _run_lifespan(FastAPI())

    assert calls == ["create_db_tables", "drain", "dispose_engine"]


async def test_lifespan_skips_table_creation_when_not_debug(calls: list[str], monkeypatch):
    """운영에서는 Alembic 이 유일한 스키마 경로다 — create_all 을 부르지 않는다."""
    monkeypatch.setattr(bootstrap.app_settings, "DEBUG", False)

    await _run_lifespan(FastAPI())

    assert calls == ["drain", "dispose_engine"]


async def test_lifespan_propagates_table_creation_failure(calls: list[str], monkeypatch):
    """기동 실패를 삼키지 않는다 — 반쯤 뜬 앱이 트래픽을 받으면 안 된다."""
    monkeypatch.setattr(bootstrap.app_settings, "DEBUG", True)

    async def boom() -> None:
        raise RuntimeError("테이블 생성 실패(모의)")

    monkeypatch.setattr(bootstrap, "create_db_tables", boom)

    with pytest.raises(RuntimeError, match="모의"):
        await _run_lifespan(FastAPI())


def test_create_app_accepts_an_isolated_registry():
    """NFR-05: 주입한 registry 를 쓰고 전역 상태를 건드리지 않는다."""
    isolated = Apps()

    app = bootstrap.create_app(registry=isolated, enable_admin=False)

    assert app.state.app_registry is isolated
    assert isolated.ready is True
    assert [c.label for c in isolated.get_app_configs()] == [
        "home",
        "blog",
        "reply",
        "sns",
        "user",
        "auth",
    ]


def test_create_app_installs_health_and_baseline_middleware():
    """BC-03: health · CORS · user-info · rate limiter 가 보존된다."""
    app = bootstrap.create_app(registry=Apps(), enable_admin=False)

    assert "/health" in app.openapi()["paths"]
    assert app.state.limiter is not None
    middleware = {m.cls.__name__ for m in app.user_middleware}
    assert "CORSMiddleware" in middleware


def test_create_app_can_run_a_subset_of_apps():
    """FR-01: 주입한 목록만 설치된다 — 전역 설정과 무관하게."""
    subset = [entry for entry in INSTALLED_APPS if "blog" not in entry]

    app = bootstrap.create_app(installed_apps=subset, registry=Apps(), enable_admin=False)

    paths = set(app.openapi()["paths"])
    assert not any("/blog/" in path for path in paths)
    assert any("/home/" in path for path in paths)
