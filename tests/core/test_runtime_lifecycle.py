"""Phase 1 — 비동기 runtime 과 자원 수명 계약 (development-plan §9).

여기서 보는 것은 "기능이 동작하는가"가 아니라 **자원이 반드시 닫히는가**다.
이 구간의 결함은 개발 중에는 보이지 않고 운영에서 커넥션 누수·좀비 프로세스로만
드러난다 — 그래서 실행 순서와 예산을 계약으로 못 박는다.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.db import session as db_session
from app.core.middlewares.background_tasks import BackgroundTaskRunner


# =============================================================================
# drain — timeout 이후 취소 회수
# =============================================================================
async def test_drain_waits_for_tasks_that_finish_in_time():
    """제 시간에 끝나는 태스크는 그대로 완료된다."""
    runner = BackgroundTaskRunner()
    finished: list[str] = []

    async def quick() -> None:
        await asyncio.sleep(0.01)
        finished.append("done")

    runner.spawn(quick())
    await runner.drain(timeout=1.0)

    assert finished == ["done"]
    assert runner.cancelled == 0


async def test_drain_cancels_and_reaps_stragglers():
    """timeout 을 넘긴 태스크는 취소하고 **회수까지** 한다.

    취소만 하고 반환하면 태스크의 ``finally``(세션 rollback/close)가 실행되기 전에
    DB engine dispose 로 넘어간다. 그러면 이미 닫힌 pool 을 만지는 태스크가 남는다.
    """
    runner = BackgroundTaskRunner()
    cleaned: list[str] = []

    async def straggler() -> None:
        try:
            await asyncio.sleep(10)
        finally:
            # 실제 코드에서는 여기가 session.rollback()/close() 다.
            cleaned.append("cleanup")

    runner.spawn(straggler())
    await runner.drain(timeout=0.05)

    assert cleaned == ["cleanup"], "취소한 태스크의 finally 가 실행되지 않았다"
    assert runner.cancelled == 1
    assert runner.active == 0, "추적 집합이 비워지지 않았다"


async def test_drain_budget_leaves_room_for_cancellation():
    """대기 예산과 취소 회수 예산이 분리돼 있다.

    바깥 guard 와 같은 값을 대기에 쓰면 취소 회수 도중 잘린다 — 정확히 그
    회수가 필요한 순간에.
    """
    from app.core import resources

    assert 0 < resources.DRAIN_WAIT_RATIO < 1, "대기 몫이 전체 예산과 같으면 회수가 잘린다"

    wait_budget = resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS * resources.DRAIN_WAIT_RATIO
    reclaim_budget = resources.BACKGROUND_DRAIN_TIMEOUT_SECONDS - wait_budget
    assert (
        reclaim_budget >= 1.0
    ), f"취소 회수 예산이 {reclaim_budget:.1f}s 뿐이다 — finally 가 끝나기 전에 잘린다"


# =============================================================================
# 세션 Dependency 명명 (ADR-009)
# =============================================================================
@pytest.mark.parametrize(
    "removed",
    ["get_session", "get_read_session", "get_write_session"],
)
def test_deprecated_aliases_are_gone(removed: str):
    """옛 이름은 Phase 7 에서 제거됐다 (ADR-009).

    전환기에는 **같은 객체**로 둔 별칭이었다 — 이름만 바꾸면
    ``dependency_overrides[get_session]`` 을 쓰는 테스트가 조용히 어긋나기 때문이다
    (override 는 키가 안 맞아도 에러가 아니라 그냥 적용되지 않는다). 호출부 전환이
    끝나 사용처가 0건임을 확인한 뒤 지웠다.

    되살아나면 이름이 다시 둘이 되고, 어느 쪽으로 override 해야 하는지가 애매해진다.
    """
    assert not hasattr(
        db_session, removed
    ), f"{removed} 가 되살아났다 — ADR-009 를 뒤집으려면 새 ADR 이 필요하다"
    from app.core import db as db_package

    assert removed not in db_package.__all__, f"{removed} 가 패키지 __all__ 에 남아 있다"


def test_new_names_carry_the_db_session_marker():
    """이름만으로 HTTP 세션·사용자 세션과 구분돼야 한다 (development-plan §9.8)."""
    for name in ("get_routed_db_session", "get_read_only_db_session", "get_writer_db_session"):
        assert "db_session" in name
        assert hasattr(db_session, name)


def test_write_dependencies_use_the_writer_session():
    """쓰기 경로는 routed 가 아니라 **writer** 세션에 고정된다.

    routed 세션은 첫 SELECT 가 replica 로 샐 수 있다. 쓰기 핸들러가 방금 쓴 것을
    다시 읽으면 복제 지연만큼 과거를 본다.
    """
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in (repo_root / "app" / "features").rglob("*_dependencies.py"):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Depends":
                target = getattr(node.args[0], "id", "") if node.args else ""
                if target == "get_routed_db_session":
                    offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")

    assert not offenders, (
        f"기능 dependency 가 routed 세션을 쓴다: {offenders} — "
        "쓰기는 get_writer_db_session, 조회는 get_read_only_db_session 이다"
    )


# =============================================================================
# /ready — liveness 와 분리
# =============================================================================
def test_readiness_returns_503_when_db_is_unavailable(monkeypatch: pytest.MonkeyPatch):
    """DB 를 못 쓰면 503 — 그리고 실패 원인을 응답에 싣지 않는다."""
    from app.core import bootstrap

    async def boom(timeout: float = 0.0) -> None:
        raise RuntimeError("mysql+aiomysql://root:SUPERSECRET@db:3306/app 접속 실패")

    monkeypatch.setattr(bootstrap, "ping_writer_db", boom)

    app = bootstrap.create_app()
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/ready")

    assert response.status_code == 503
    assert "SUPERSECRET" not in response.text, "readiness 응답에 자격증명이 실렸다"
    assert "aiomysql" not in response.text


def test_readiness_returns_200_when_db_answers(monkeypatch: pytest.MonkeyPatch):
    from app.core import bootstrap

    async def ok(timeout: float = 0.0) -> None:
        return None

    monkeypatch.setattr(bootstrap, "ping_writer_db", ok)

    app = bootstrap.create_app()
    client = TestClient(app)
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_liveness_does_not_touch_the_database(monkeypatch: pytest.MonkeyPatch):
    """`/health` 는 DB 를 보지 않는다.

    liveness 가 DB 에 의존하면, DB 가 잠깐 흔들릴 때 오케스트레이터가 **멀쩡한
    프로세스를 죽인다**. 그건 복구가 아니라 장애 증폭이다.
    """
    from app.core import bootstrap

    called: list[str] = []

    async def spy(timeout: float = 0.0) -> None:
        called.append("ping")

    monkeypatch.setattr(bootstrap, "ping_writer_db", spy)

    app = bootstrap.create_app()
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert called == [], "liveness 가 DB 를 확인했다"


def test_readiness_is_in_the_openapi_contract():
    from app.core.bootstrap import create_app

    schema = create_app().openapi()
    assert "/ready" in schema["paths"]
    assert "503" in schema["paths"]["/ready"]["get"]["responses"]


# =============================================================================
# 커넥션 풀 예산
# =============================================================================
def test_total_connection_estimate_counts_every_engine():
    """총 연결 수 계산이 writer·reader·background 와 프로세스 수를 모두 반영한다."""
    from config import DatabaseSettings

    settings = DatabaseSettings(
        DB_POOL_SIZE=10,
        DB_MAX_OVERFLOW=5,
        DB_BACKGROUND_POOL_SIZE=2,
        DB_BACKGROUND_MAX_OVERFLOW=1,
        DB_WORKER_PROCESSES=4,
    )

    # (10+5) x 1 엔진 + (2+1) = 18, x 4 프로세스 = 72
    assert settings.max_total_connections == 72


def test_pool_settings_that_exceed_the_server_limit_are_rejected():
    """상한을 넘는 풀 설정은 기동 시점에 막는다.

    이 초과는 평소엔 안 보이다가 트래픽이 몰릴 때만 "Too many connections" 로
    터진다 — 가장 나쁜 시점에 드러나는 종류의 설정 오류다.
    """
    from pydantic import ValidationError

    from config import DatabaseSettings

    with pytest.raises(ValidationError, match="DB_MAX_SERVER_CONNECTIONS"):
        DatabaseSettings(
            DB_POOL_SIZE=50,
            DB_MAX_OVERFLOW=50,
            DB_WORKER_PROCESSES=8,
            DB_MAX_SERVER_CONNECTIONS=100,
        )


def test_unknown_server_limit_skips_validation():
    """서버 상한을 모르면 검증하지 않는다 — 모르는 값을 지어내지 않는다."""
    from config import DatabaseSettings

    settings = DatabaseSettings(
        DB_POOL_SIZE=50,
        DB_MAX_OVERFLOW=50,
        DB_BACKGROUND_POOL_SIZE=10,
        DB_BACKGROUND_MAX_OVERFLOW=10,
        DB_WORKER_PROCESSES=8,
        DB_MAX_SERVER_CONNECTIONS=0,
    )
    # ((50+50) x 1 엔진 + (10+10)) x 8 프로세스 = 960. 상한을 모르면 막지 않는다.
    assert settings.max_total_connections == 960


def test_engines_use_the_configured_pool_size():
    """하드코딩이 아니라 설정을 실제로 반영한다."""
    from config import db_settings

    assert db_session.engine.pool.size() == db_settings.DB_POOL_SIZE


# =============================================================================
# Celery worker 자원 종료
# =============================================================================
def test_worker_shutdown_is_a_noop_without_a_loop():
    """태스크를 한 번도 실행하지 않은 worker 는 닫을 것이 없다."""
    from app.celery.lifecycle import shutdown_worker_resources
    from app.celery.task import clear_worker_loop, get_worker_loop

    clear_worker_loop()
    shutdown_worker_resources()

    assert get_worker_loop() is None


def test_worker_shutdown_closes_the_loop(monkeypatch: pytest.MonkeyPatch):
    """worker 가 만든 루프와 그 루프에 묶인 pool 을 닫는다.

    닫지 않으면 커넥션이 서버 쪽에 남고 "Event loop is closed" 경고가 쏟아진다.
    """
    from app.celery import lifecycle, task

    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task, "_worker_loop", loop)

    disposed: list[str] = []

    async def fake_dispose() -> None:
        disposed.append("dispose")

    monkeypatch.setattr(lifecycle, "dispose_engine", fake_dispose)

    lifecycle.shutdown_worker_resources()

    assert disposed == ["dispose"], "루프가 살아 있는 동안 dispose 하지 않았다"
    assert loop.is_closed(), "event loop 를 닫지 않으면 프로세스가 종료되지 않는다"
    assert task.get_worker_loop() is None


def test_worker_shutdown_closes_the_loop_even_if_dispose_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    """dispose 가 실패해도 루프는 닫는다 — 안 닫으면 프로세스가 안 죽는다."""
    from app.celery import lifecycle, task

    loop = asyncio.new_event_loop()
    monkeypatch.setattr(task, "_worker_loop", loop)

    async def boom() -> None:
        raise RuntimeError("dispose 실패(모의)")

    monkeypatch.setattr(lifecycle, "dispose_engine", boom)

    lifecycle.shutdown_worker_resources()

    assert loop.is_closed()
    assert task.get_worker_loop() is None


def test_fastapi_lifespan_does_not_close_celery_resources():
    """소유권 분리 — FastAPI 자원 관리자가 Celery 자원을 import 하지 않는다.

    FastAPI lifespan 은 worker 프로세스에서 돌지 않는다. 거기서 Celery 루프를
    닫으려 하면 **다른 프로세스의 자원**을 만지는 셈이고, 반대로 worker 가
    FastAPI 자원을 닫아도 마찬가지다. 소유권을 코드 수준에서 갈라 둔다.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "app" / "core" / "resources.py").read_text(
        encoding="utf-8"
    )

    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    offenders = [name for name in imported if name.startswith("app.celery")]
    assert not offenders, f"resources.py 가 Celery 자원을 import 한다: {offenders}"
