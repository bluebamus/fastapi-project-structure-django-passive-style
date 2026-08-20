"""브라우저 테스트 하네스 — 실제 uvicorn 을 띄우고 Chromium 으로 연다.

`TestClient` 로는 이 층을 볼 수 없다. Scalar 는 **브라우저에서 JavaScript 로**
`/openapi.json` 을 가져와 화면을 그린다. HTTP 응답이 200 이라는 것과 문서가 실제로
그려진다는 것은 다른 이야기다 — 스키마가 규격에 맞아도 렌더러가 죽으면 사용자가 보는
것은 빈 화면이다.

**async API 를 쓴다.** `playwright.sync_api` 는 자기 이벤트 루프를 돌리는데, 이
저장소는 `asyncio_mode=auto` 라 pytest-asyncio 가 같은 스레드에서 루프를 돌린다.
둘이 겹치면 ``RuntimeError: This event loop is already running`` 으로 **브라우저와
무관한 테스트 수백 개가 함께 깨진다**(실제로 38 failed / 124 errors 를 봤다).
마커로 나눠 돌리면 가려지지만, 마커 없이 전체를 돌리는 순간 드러난다.

브라우저가 없으면 **skip 하지 않고 실패한다**. MySQL 통합과 같은 이유다(NFR-012) —
인프라가 없어 안 돈 것을 통과로 세면 "전체 green" 이 거짓말이 된다. 준비 명령은
실패 메시지에 적혀 있다.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 서버가 뜰 때까지 기다리는 상한. 넘으면 실패다 — 조용히 넘어가지 않는다.
STARTUP_TIMEOUT_SECONDS = 40.0

#: 브라우저 준비 명령. 실패했을 때 사용자가 바로 실행할 수 있도록 메시지에 넣는다.
INSTALL_HINT = "uv run python -m playwright install chromium"


def _free_port() -> int:
    """비어 있는 TCP 포트를 하나 잡는다.

    고정 포트를 쓰면 테스트를 두 개 동시에 돌릴 때 충돌한다 — 검수 게이트를 병렬로
    돌리는 것이 이 저장소의 요구사항이다.
    """
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_until_serving(port: int, process: subprocess.Popen[bytes]) -> None:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = b""
            if process.stdout is not None:
                output = process.stdout.read() or b""
            tail = "\n".join(output.decode("utf-8", "replace").strip().splitlines()[-15:])
            raise RuntimeError(f"uvicorn 이 시작 중에 종료했다 (코드 {process.returncode})\n{tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.2)
    raise TimeoutError(f"{STARTUP_TIMEOUT_SECONDS:.0f}s 안에 uvicorn 이 뜨지 않았다")


@pytest.fixture(scope="session")
def live_server() -> Iterator[str]:
    """실제 uvicorn 프로세스를 띄우고 base URL 을 돌려준다.

    `DEBUG=true` 여야 `/docs` 가 열린다 — 운영 모드에서는 의도적으로 차단된다.

    **DB 가 필요하다.** Scalar 자체는 `/openapi.json` 만 읽지만, 개발 모드 startup 이
    `create_db_tables()` 로 DB 에 붙는다. 붙지 못하면 앱이 아예 뜨지 않는다 — 그래서
    `compose.test.yaml` 의 테스트 인스턴스를 가리킨다. 자격증명은 통합 테스트
    하네스가 소유한 값을 그대로 쓴다(여기서 다시 적으면 두 곳이 갈린다).

    stdout/stderr 는 버리지 않고 파이프로 받는다 — 시작이 실패했을 때 그 이유가
    보여야 한다(처음에 DEVNULL 로 버려서 "연결 거부" 만 보고 원인을 몰랐다).
    """
    from tests.integration.conftest import (
        MYSQL_DATABASE,
        MYSQL_HOST,
        MYSQL_PASSWORD,
        MYSQL_PORT,
        MYSQL_USER,
    )

    port = _free_port()
    # `-X utf8` 은 저장소 계약이다(C-7). Windows 기본 인코딩(cp949)으로 자식이 쓰면
    # 부모가 stderr 를 디코딩하다 터져 **실패 원인이 통째로 사라진다**.
    # 한 줄로 두는 이유: 계약 검사가 줄 단위라 여러 줄로 쪼개면 못 본다.
    launcher = [sys.executable, "-X", "utf8", "-m", "uvicorn"]
    process = subprocess.Popen(
        [
            *launcher,
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env={
            **os.environ,
            "DEBUG": "true",
            "MYSQL_HOST": MYSQL_HOST,
            "MYSQL_PORT": str(MYSQL_PORT),
            "MYSQL_USER": MYSQL_USER,
            "MYSQL_PASSWORD": MYSQL_PASSWORD,
            "MYSQL_DATABASE": MYSQL_DATABASE,
            "PYTHONIOENCODING": "utf-8",
        },
    )
    try:
        _wait_until_serving(port, process)
        yield f"http://127.0.0.1:{port}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


@pytest.fixture
async def docs_page(live_server: str) -> AsyncIterator:
    """`/docs` 를 열고 Scalar 가 그려질 때까지 기다린 페이지.

    브라우저를 테스트마다 새로 띄운다. session 으로 공유하면 pytest-asyncio 가 만드는
    루프와 수명이 어긋난다 — 브라우저 객체는 자기를 만든 루프에 묶여 있다.
    7건짜리 파일이라 재사용으로 아낄 시간보다 그 복잡도가 비싸다.

    콘솔 오류와 실패한 네트워크 요청을 함께 수집한다 — 화면이 그려져도 그 아래에서
    무언가 죽고 있으면 다음 버전에서 터진다.
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - 의존성 누락 시에만
        pytest.fail(
            f"playwright 가 설치되지 않았다: {exc}. `uv sync --group dev` 후 {INSTALL_HINT}"
        )

    async with async_playwright() as playwright:
        try:
            browser = await playwright.chromium.launch()
        except Exception as exc:  # pragma: no cover - 브라우저 미설치 시에만
            pytest.fail(f"Chromium 을 띄우지 못했다: {exc}\n준비: {INSTALL_HINT}")

        page = await browser.new_page()
        page.console_errors = []  # type: ignore[attr-defined]
        page.failed_requests = []  # type: ignore[attr-defined]
        page.on(
            "console",
            lambda message: (
                page.console_errors.append(message.text) if message.type == "error" else None
            ),
        )
        page.on(
            "requestfailed",
            lambda request: page.failed_requests.append(f"{request.method} {request.url}"),
        )

        try:
            await page.goto(f"{live_server}/docs", wait_until="networkidle", timeout=30_000)
            yield page
        finally:
            await browser.close()
