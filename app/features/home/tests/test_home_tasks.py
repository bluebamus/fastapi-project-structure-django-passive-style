"""home 태스크 — 세션은 background_session, 서비스 조립은 home provider (ADR-012)."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from app.features.home import tasks
from app.features.home.dependencies import access_log_dependencies


def test_aggregate_task_registered():
    from app.celery.app import celery_app

    assert tasks.aggregate_access_stats.name == "home.aggregate_access_stats"
    assert "home.aggregate_access_stats" in celery_app.tasks


def test_task_builds_the_service_through_the_provider(monkeypatch: pytest.MonkeyPatch):
    """태스크가 연 background 세션이 provider 로 들어가고, 그 서비스의 통계를 돌려준다."""
    session = object()
    seen: list[object] = []

    @asynccontextmanager
    async def fake_background_session():
        yield session

    class FakeService:
        async def get_stats(self) -> SimpleNamespace:
            return SimpleNamespace(total_count=7)

    def fake_build(received: object) -> FakeService:
        seen.append(received)
        return FakeService()

    monkeypatch.setattr(tasks, "background_session", fake_background_session)
    monkeypatch.setattr(tasks, "build_user_access_log_service", fake_build)
    # 워커 영속 루프를 테스트 프로세스에 남기지 않는다.
    monkeypatch.setattr(tasks, "run_async", asyncio.run)

    assert tasks.aggregate_access_stats() == {"total": 7}
    assert seen == [session]


async def test_http_provider_reuses_the_session_builder(monkeypatch: pytest.MonkeyPatch):
    session = object()
    built = object()
    monkeypatch.setattr(
        access_log_dependencies,
        "build_user_access_log_service",
        lambda received: built if received is session else None,
    )

    assert await access_log_dependencies.get_access_log_service(session) is built  # type: ignore[arg-type]


def test_builder_passes_the_session_and_timezone():
    from config import timezone_settings

    session = object()
    service = access_log_dependencies.build_user_access_log_service(session)  # type: ignore[arg-type]

    assert service.session is session
    assert service.timezone is timezone_settings
