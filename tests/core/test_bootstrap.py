"""``create_app()`` 조립과 lifespan 계약 (FR-07·BC-03·NFR-05).

lifespan 은 지금까지 어떤 테스트도 실행하지 않던 구간이다 — ``TestClient`` 를 context
manager 로 쓰지 않으면 startup/shutdown 이 돌지 않기 때문이다. 그런데 여기 있는 두
분기(DEBUG 여부)와 종료 시 drain 순서가 배포에서 가장 먼저 문제를 일으키는 코드다.

DB 호출은 대체한다 — 검증 대상은 "테이블을 만드는가" 가 아니라 **조립부가 어떤 순서로
무엇을 부르는가** 이고, 실제 테이블 생성은 migration 테스트가 따로 본다.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core import bootstrap, resources
from app.core.apps import Apps
from config import INSTALLED_APPS


class _FakeRedis:
    async def ping(self) -> bool:
        return True

    async def info(self, section: str | None = None) -> dict[str, str]:
        return {"redis_version": "7.4.0"}

    async def aclose(self) -> None:
        return None


class _FakeRedisFactory:
    @staticmethod
    def from_url(*args, **kwargs) -> _FakeRedis:
        return _FakeRedis()


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """자원 관리자가 부르는 외부 호출을 순서대로 기록한다."""
    recorded: list[str] = []

    async def fake_create_tables(*, registry: Apps | None = None, populate: bool = True) -> int:
        recorded.append("create_db_tables")
        return 1

    async def fake_dispose() -> None:
        recorded.append("dispose_engine")

    class _Tasks:
        async def drain(self, timeout: float = 0.0) -> None:
            recorded.append("drain")

    # 기본값: registry 에 테이블이 있다고 본다. 0개 분기는 개별 테스트가 덮어쓴다.
    monkeypatch.setattr(resources, "owned_tables", lambda registry: ["t"])
    monkeypatch.setattr(resources, "create_db_tables", fake_create_tables)
    monkeypatch.setattr(resources, "dispose_engine", fake_dispose)
    monkeypatch.setattr(resources, "access_log_tasks", _Tasks())
    monkeypatch.setattr(resources, "Redis", _FakeRedisFactory)
    return recorded


def _app() -> FastAPI:
    """lifespan 이 읽는 ``app.state.app_registry`` 만 갖춘 빈 앱(조립은 ``create_app`` 의 몫)."""
    app = FastAPI()
    app.state.app_registry = Apps()
    return app


async def _run_lifespan(app: FastAPI) -> None:
    async with bootstrap.lifespan(app):
        pass


async def test_lifespan_creates_tables_in_debug(calls: list[str], monkeypatch):
    """DEBUG=True 면 테이블을 만들고, 종료 시 drain 후 엔진을 정리한다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    await _run_lifespan(_app())

    assert calls == ["create_db_tables", "drain", "dispose_engine"]


async def test_lifespan_skips_table_creation_when_not_debug(calls: list[str], monkeypatch):
    """운영에서는 Alembic 이 유일한 스키마 경로다 — create_all 을 부르지 않는다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", False)

    await _run_lifespan(_app())

    assert calls == ["drain", "dispose_engine"]


async def test_lifespan_skips_database_entirely_when_no_models(calls: list[str], monkeypatch):
    """소유 테이블이 0개면 DB 에 **접속조차** 하지 않는다.

    모델이 하나도 없는 앱이 "테이블 0개를 만들려고 DB 가 떠 있어야 하는" 상태가
    되면, registry 를 비우는 것만으로 기동이 깨진다.
    """
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)
    monkeypatch.setattr(resources, "owned_tables", lambda registry: [])

    app = _app()
    await _run_lifespan(app)

    assert "create_db_tables" not in calls
    assert calls == ["drain", "dispose_engine"]


async def test_lifespan_propagates_table_creation_failure(calls: list[str], monkeypatch):
    """기동 실패를 삼키지 않는다 — 반쯤 뜬 앱이 트래픽을 받으면 안 된다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    async def boom(**_: object) -> int:
        raise RuntimeError("테이블 생성 실패(모의)")

    monkeypatch.setattr(resources, "create_db_tables", boom)

    with pytest.raises(RuntimeError, match="모의"):
        await _run_lifespan(_app())


async def test_redis_connection_failure_stops_startup(calls: list[str], monkeypatch):
    """필수 Redis의 PING 실패를 삼키지 않고 이미 등록된 자원은 정리한다."""

    class _UnavailableRedis(_FakeRedis):
        async def ping(self) -> bool:
            raise RedisConnectionError("Redis unavailable")

        async def aclose(self) -> None:
            calls.append("redis_close")

    class _UnavailableRedisFactory:
        @staticmethod
        def from_url(*args, **kwargs) -> _UnavailableRedis:
            return _UnavailableRedis()

    monkeypatch.setattr(resources, "Redis", _UnavailableRedisFactory)
    app = _app()

    with pytest.raises(RedisConnectionError):
        await _run_lifespan(app)

    assert calls == ["redis_close", "dispose_engine"]
    assert app.state.redis is None
    assert app.state.resources is None


async def test_startup_failure_runs_the_same_cleanup_path(calls: list[str], monkeypatch):
    """startup 이 깨져도 정상 종료와 **같은** cleanup 이 돈다.

    실패 경로에만 해제가 빠지면 "개발에서는 멀쩡한데 기동 실패가 반복될 때만
    커넥션이 새는" 상태가 된다 — 재현이 가장 어려운 종류다.
    """
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    async def boom(**_: object) -> int:
        raise RuntimeError("모의 실패")

    monkeypatch.setattr(resources, "create_db_tables", boom)

    with pytest.raises(RuntimeError):
        await _run_lifespan(_app())

    assert calls == [
        "drain",
        "dispose_engine",
    ], f"실패 경로의 cleanup 이 정상 경로와 다르다: {calls}"


async def test_resources_reference_is_cleared_after_shutdown(calls: list[str], monkeypatch):
    """종료 후 app.state 가 닫힌 자원을 가리키지 않는다."""
    monkeypatch.setattr(resources.app_settings, "DEBUG", False)

    app = _app()
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

    await _run_lifespan(_app())

    assert calls == [
        "drain",
        "dispose_engine",
    ], "drain 실패가 engine dispose 를 건너뛰게 만들었다 — 커넥션이 샌다"


def test_create_app_accepts_an_isolated_registry():
    """NFR-05: 주입한 registry 를 쓰고 전역 상태를 건드리지 않는다."""
    isolated = Apps()

    app = bootstrap.create_app(registry=isolated, admin_disabled=True)

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
    app = bootstrap.create_app(registry=Apps(), admin_disabled=True)

    assert "/health" in app.openapi()["paths"]
    middleware = {m.cls.__name__ for m in app.user_middleware}
    assert "CORSMiddleware" in middleware


def test_create_app_can_run_a_subset_of_apps():
    """FR-01: 주입한 목록만 설치된다 — 전역 설정과 무관하게."""
    subset = [entry for entry in INSTALLED_APPS if "blog" not in entry]

    app = bootstrap.create_app(installed_apps=subset, registry=Apps(), admin_disabled=True)

    paths = set(app.openapi()["paths"])
    assert not any("/blog/" in path for path in paths)
    assert any("/home/" in path for path in paths)


async def test_lifespan_creates_only_the_injected_registrys_tables(monkeypatch, tmp_path):
    """lifespan 은 ``create_app`` 이 조립에 쓴 registry 의 테이블만 만든다(service-hardening F-012).

    예전에는 ``_prepare_database`` 가 전역 registry 를 ``config.INSTALLED_APPS`` 로 채워 셌다 —
    blog 를 뺀 앱도 ``posts`` 테이블을 만들었다. 실제 DDL 을 SQLite 파일에 실행해 확인한다.
    """
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.db import session as db_session

    sqlite_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}")

    async def _noop() -> None:
        return None

    class _Tasks:
        async def drain(self, timeout: float = 0.0) -> None:
            return None

    monkeypatch.setattr(db_session, "engine", sqlite_engine)
    monkeypatch.setattr(resources, "dispose_engine", _noop)
    monkeypatch.setattr(resources, "access_log_tasks", _Tasks())
    monkeypatch.setattr(resources, "Redis", _FakeRedisFactory)
    monkeypatch.setattr(resources.app_settings, "DEBUG", True)

    subset = [e for e in INSTALLED_APPS if e.split(".")[2] in {"home", "catalog"}]
    registry = Apps()
    app = bootstrap.create_app(installed_apps=subset, registry=registry, admin_disabled=True)
    expected = {model.__table__.name for model in registry.get_models()}

    try:
        async with bootstrap.lifespan(app):
            assert app.state.resources.table_count == len(expected)
        async with sqlite_engine.connect() as conn:
            created = set(await conn.run_sync(lambda c: sa_inspect(c).get_table_names()))
    finally:
        await sqlite_engine.dispose()

    assert expected == {"user_access_logs", "catalog_products"}
    assert created == expected, f"설치하지 않은 앱의 테이블이 생겼다: {created - expected}"


def _app_exception_log_records(status_code: int) -> list[logging.LogRecord]:
    """``AppException`` 하나를 핸들러에 태워 그 로그 레코드를 돌려준다."""
    from fastapi.testclient import TestClient

    from app.core.exception import AppException

    app = bootstrap.create_app(registry=Apps(), admin_disabled=True)

    @app.get("/raise")
    async def _raise() -> None:
        raise AppException(
            message="모의", detail={"input": "민감할 수 있는 입력"}, status_code=status_code
        )

    records: list[logging.LogRecord] = []

    class _Recorder(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if record.getMessage().startswith("[AppException]"):
                records.append(record)

    handler = _Recorder(logging.DEBUG)
    bootstrap.logger.addHandler(handler)
    try:
        response = TestClient(app).get("/raise")
    finally:
        bootstrap.logger.removeHandler(handler)
    assert response.status_code == status_code
    return records


def test_client_error_app_exception_is_logged_as_warning_without_detail():
    """4xx 는 클라이언트 입력 문제다 — ERROR 로 남기면 운영 경보가 클라이언트 실수로 울린다(F-013)."""
    (record,) = _app_exception_log_records(404)

    assert record.levelno == logging.WARNING
    assert not hasattr(record, "detail"), "4xx 로그에 detail(입력값)이 실렸다"


def test_server_error_app_exception_is_logged_as_error():
    (record,) = _app_exception_log_records(503)

    assert record.levelno == logging.ERROR
