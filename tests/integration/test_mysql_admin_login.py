"""MySQL 8.4 — 운영 절차 그대로 만든 슈퍼유저로 /admin 에 로그인한다 (admin-login ADR-001).

``python -m scripts.create_superuser --password-stdin`` 을 **별도 프로세스**로 실행해 MySQL 에
계정을 만들고(임의 사용자명), 같은 DB 를 보는 앱으로 로그인 흐름을 확인한다. SQLite 통합
테스트(``tests/core/test_admin_login_flow.py``)와 같은 흐름을 MySQL 방언·드라이버·Argon2 해시
저장 길이로 다시 본다. Redis 는 fakeredis 다(레이트 리밋은 단위 테스트가 본다).
"""

from __future__ import annotations

import os
import subprocess  # noqa: S404 - 운영 절차 그대로 스크립트를 실행한다
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from fakeredis.aioredis import FakeRedis
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.apps import Apps
from app.core.bootstrap import create_app
from tests.integration.conftest import (
    MYSQL_DATABASE,
    MYSQL_HOST,
    MYSQL_PASSWORD,
    MYSQL_PORT,
    MYSQL_USER,
)

pytestmark = pytest.mark.mysql

REPO_ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "Mysql-admin-pw-123"


def _create_superuser(username: str) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "MYSQL_HOST": MYSQL_HOST,
        "MYSQL_PORT": str(MYSQL_PORT),
        "MYSQL_USER": MYSQL_USER,
        "MYSQL_PASSWORD": MYSQL_PASSWORD,
        "MYSQL_DATABASE": MYSQL_DATABASE,
        "PYTHONIOENCODING": "utf-8",
    }
    # 한 줄로 두는 이유: `-X utf8` 계약 검사가 줄 단위다(tests/test_layering_and_openapi.py).
    launcher = [sys.executable, "-X", "utf8", "-m", "scripts.create_superuser"]
    return subprocess.run(  # noqa: S603 - 인터프리터·모듈이 고정돼 있다
        [*launcher, "--username", username, "--email", f"{username}@x.com", "--password-stdin"],
        input=f"{PASSWORD}\n",
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


async def test_script_created_superuser_logs_in_to_admin_on_mysql(mysql_session_maker):
    username = f"mysql-admin-{uuid4().hex[:8]}"
    created = _create_superuser(username)
    assert created.returncode == 0, created.stderr[-2000:]

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        async with mysql_session_maker() as session:
            yield session

    app = create_app(registry=Apps(), admin_disabled=False)
    app.state.admin.authentication_backend.credentials.session_factory = factory
    redis = FakeRedis()
    app.state.redis = redis
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/admin/")).status_code == 302
        wrong = await client.post(
            "/admin/login", data={"username": username, "password": "wrong-password"}
        )
        assert wrong.status_code == 400
        ok = await client.post("/admin/login", data={"username": username, "password": PASSWORD})
        assert ok.status_code == 302
        assert (await client.get("/admin/")).status_code == 200
        await client.get("/admin/logout")
        assert (await client.get("/admin/")).status_code == 302
    await redis.aclose()
