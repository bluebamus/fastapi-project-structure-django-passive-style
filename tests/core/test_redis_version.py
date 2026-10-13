"""Redis 최소 버전 (log-redaction-fixes ADR-004).

- 기동 확인: ``INFO server`` 가 최소 버전 미만이면 기동을 멈추고, 이상이면 통과하며, INFO 를
  쓸 수 없으면(관리형 Redis·fakeredis) WARNING 후 계속한다.
- 계약: 소스가 실제로 쓰는 명령이 요구하는 버전 <= ``REDIS_MIN_VERSION``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import FastAPI
from redis.exceptions import ResponseError

from app.core import bootstrap, resources
from app.core import redis as core_redis
from app.core.apps import Apps
from app.core.redis import REDIS_MIN_VERSION, UnsupportedRedisVersion, ensure_redis_version

APP_DIR = Path(core_redis.__file__).resolve().parents[1]


class _InfoRedis:
    def __init__(self, info: dict[str, str] | Exception) -> None:
        self._info = info

    async def info(self, section: str | None = None) -> dict[str, str]:
        assert section == "server"
        if isinstance(self._info, Exception):
            raise self._info
        return self._info


@pytest.mark.parametrize("version", ["6.2.14", "6.0.0", "5.0.7"])
async def test_older_server_stops_startup(version: str):
    with pytest.raises(UnsupportedRedisVersion, match=re.escape(version)):
        await ensure_redis_version(_InfoRedis({"redis_version": version}))  # type: ignore[arg-type]


@pytest.mark.parametrize("version", ["7.0.0", "7.4.2", "8.0.1", "10.0.0"])
async def test_supported_server_passes(version: str):
    await ensure_redis_version(_InfoRedis({"redis_version": version}))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "info",
    [ResponseError("unknown command 'info'"), {"redis_version": ""}, {}],
    ids=["info-blocked", "empty", "missing"],
)
async def test_unknown_version_warns_and_continues(info, caplog: pytest.LogCaptureFixture):
    with caplog.at_level(logging.WARNING):
        await ensure_redis_version(_InfoRedis(info))  # type: ignore[arg-type]

    assert any("Redis 버전 확인 생략" in r.getMessage() for r in caplog.records)


async def test_fakeredis_used_by_tests_does_not_break_startup(caplog: pytest.LogCaptureFixture):
    """테스트가 쓰는 fakeredis 는 INFO 를 모른다(ResponseError) — 경고 경로로 간다."""
    with caplog.at_level(logging.WARNING):
        await ensure_redis_version(FakeRedis())

    assert any("Redis 버전 확인 생략" in r.getMessage() for r in caplog.records)


async def test_lifespan_refuses_an_old_redis(monkeypatch: pytest.MonkeyPatch):
    """lifespan 이 연결 직후 버전을 보고, 거부해도 클라이언트를 닫는다."""
    closed: list[bool] = []

    class _OldRedis:
        async def ping(self) -> bool:
            return True

        async def info(self, section: str | None = None) -> dict[str, str]:
            return {"redis_version": "6.2.14"}

        async def aclose(self) -> None:
            closed.append(True)

    class _Factory:
        @staticmethod
        def from_url(*args: object, **kwargs: object) -> _OldRedis:
            return _OldRedis()

    async def _noop() -> None:
        return None

    monkeypatch.setattr(resources, "Redis", _Factory)
    monkeypatch.setattr(resources, "dispose_engine", _noop)
    app = FastAPI()
    app.state.app_registry = Apps()

    with pytest.raises(UnsupportedRedisVersion):
        async with bootstrap.lifespan(app):
            pass

    assert closed == [True]
    assert app.state.redis is None


# 명령(형태) -> 소스 탐지 정규식 -> 그 형태가 처음 들어간 Redis 버전
_COMMAND_VERSIONS: tuple[tuple[str, str, tuple[int, int]], ...] = (
    ("EXPIRE ... NX", r"\.expire\([^)]*\bnx=True", (7, 0)),
    ("GETDEL", r"\.getdel\(", (6, 2)),
    ("SET ... NX/EX", r"\.set\([^)]*\b(?:nx|ex)=", (2, 6)),
)


def test_min_version_covers_every_command_the_code_uses():
    sources = "\n".join(p.read_text(encoding="utf-8") for p in APP_DIR.rglob("*.py"))
    used = [
        (name, need) for name, pattern, need in _COMMAND_VERSIONS if re.search(pattern, sources)
    ]

    assert used, "명령 탐지 정규식이 아무것도 찾지 못했다 — 소스 경로나 정규식이 틀렸다"
    for name, need in used:
        assert REDIS_MIN_VERSION >= need, f"{name} 은 Redis {need} 이상이 필요하다"
    # 최소 버전은 실제로 쓰는 명령의 최댓값이다(근거 없이 높이지도 않는다).
    assert max(need for _, need in used) == REDIS_MIN_VERSION
