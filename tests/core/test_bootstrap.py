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

from app.core import bootstrap, resources
from app.core.apps import Apps
from config import INSTALLED_APPS


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """자원 관리자가 부르는 외부 호출을 순서대로 기록한다."""
    recorded: list[str] = []

    async def fake_create_tables(*, populate: bool = True) -> int:
        recorded.append("create_db_tables")
        return 1

    async def fake_dispose() -> None:
        recorded.append("dispose_engine")

    class _Tasks:
        async def drain(self, timeout: float = 0.0) -> None:
            recorded.append("drain")

    # 기본값: registry 에 테이블이 있다고 본다. 0개 분기는 개별 테스트가 덮어쓴다.
    monkeypatch.setattr(resources, "owned_tables", lambda: ["t"])
    monkeypatch.setattr(resources, "create_db_tables", fake_create_tables)
    monkeypatch.setattr(resources, "dispose_engine", fake_dispose)
    monkeypatch.setattr(resources, "access_log_tasks", _Tasks())
    return recorded


async def _run_lifespan(app: FastAPI) -> None:
    async with bootstrap.lifespan(app):
        pass


async def test_lifespan_creates_tables_in_debug(calls: list[str], monkeypatch):
    """DEBUG=True 면 테이블을 만들고, 종료 시 drain 후 엔진을 정리한다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    await _run_lifespan(FastAPI())

    assert calls == ["create_db_tables", "drain", "dispose_engine"]


async def test_lifespan_skips_table_creation_when_not_debug(calls: list[str], monkeypatch):
    """운영에서는 Alembic 이 유일한 스키마 경로다 — create_all 을 부르지 않는다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", False)

    await _run_lifespan(FastAPI())

    assert calls == ["drain", "dispose_engine"]


async def test_lifespan_skips_database_entirely_when_no_models(calls: list[str], monkeypatch):
    """소유 테이블이 0개면 DB 에 **접속조차** 하지 않는다.

    모델이 하나도 없는 앱이 "테이블 0개를 만들려고 DB 가 떠 있어야 하는" 상태가
    되면, registry 를 비우는 것만으로 기동이 깨진다.
    """
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)
    monkeypatch.setattr(resources, "owned_tables", list)

    app = FastAPI()
    await _run_lifespan(app)

    assert "create_db_tables" not in calls
    assert calls == ["drain", "dispose_engine"]


async def test_lifespan_propagates_table_creation_failure(calls: list[str], monkeypatch):
    """기동 실패를 삼키지 않는다 — 반쯤 뜬 앱이 트래픽을 받으면 안 된다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    async def boom(*, populate: bool = True) -> int:
        raise RuntimeError("테이블 생성 실패(모의)")

    monkeypatch.setattr(resources, "create_db_tables", boom)

    with pytest.raises(RuntimeError, match="모의"):
        await _run_lifespan(FastAPI())


async def test_startup_failure_runs_the_same_cleanup_path(calls: list[str], monkeypatch):
    """startup 이 깨져도 정상 종료와 **같은** cleanup 이 돈다.

    실패 경로에만 해제가 빠지면 "개발에서는 멀쩡한데 기동 실패가 반복될 때만
    커넥션이 새는" 상태가 된다 — 재현이 가장 어려운 종류다.
    """
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    async def boom(*, populate: bool = True) -> int:
        raise RuntimeError("모의 실패")

    monkeypatch.setattr(resources, "create_db_tables", boom)

    with pytest.raises(RuntimeError):
        await _run_lifespan(FastAPI())

    assert calls == [
        "drain",
        "dispose_engine",
    ], f"실패 경로의 cleanup 이 정상 경로와 다르다: {calls}"


async def test_resources_reference_is_cleared_after_shutdown(calls: list[str], monkeypatch):
    """종료 후 app.state 가 닫힌 자원을 가리키지 않는다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", False)

    app = FastAPI()
    async with bootstrap.lifespan(app):
        assert app.state.resources is not None

    assert app.state.resources is None


async def test_cleanup_failure_does_not_stop_the_rest(calls: list[str], monkeypatch):
    """cleanup 하나가 실패해도 뒤따르는 cleanup 은 실행된다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", False)

    class _BrokenTasks:
        async def drain(self, timeout: float = 0.0) -> None:
            calls.append("drain")
            raise RuntimeError("drain 실패(모의)")

    monkeypatch.setattr(resources, "access_log_tasks", _BrokenTasks())

    await _run_lifespan(FastAPI())

    assert calls == [
        "drain",
        "dispose_engine",
    ], "drain 실패가 engine dispose 를 건너뛰게 만들었다 — 커넥션이 샌다"


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
        "catalog",
        "reports",
    ]


def test_create_app_installs_health_and_baseline_middleware():
    """BC-03: health · CORS · user-info 가 보존된다."""
    app = bootstrap.create_app(registry=Apps(), enable_admin=False)

    assert "/health" in app.openapi()["paths"]
    middleware = {m.cls.__name__ for m in app.user_middleware}
    assert "CORSMiddleware" in middleware


def test_create_app_can_run_a_subset_of_apps():
    """FR-01: 주입한 목록만 설치된다 — 전역 설정과 무관하게."""
    subset = [entry for entry in INSTALLED_APPS if "blog" not in entry]

    app = bootstrap.create_app(installed_apps=subset, registry=Apps(), enable_admin=False)

    paths = set(app.openapi()["paths"])
    assert not any("/blog/" in path for path in paths)
    assert any("/home/" in path for path in paths)
