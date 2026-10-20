"""L5 — 장애 주입. 이 프로젝트(``itest-passive``)의 컨테이너·프로세스에만 한다.

* Redis: 컨테이너 ``stop``/``start`` (영속 데이터 없음 — 키는 사라진다).
* MySQL primary·replica: 데이터가 tmpfs 라 ``stop`` 하면 스키마가 사라진다. 대신 ``offline_mode`` 로
  SUPER 가 아닌 연결(앱)을 끊고 새 연결을 거부한다(integration-e2e ADR-002).
* Celery worker: 하네스가 띄운 프로세스를 내렸다 올린다.

응답 코드만 보지 않는다 — 연결이 정상 HTTP 응답으로 끝났는지(keep-alive)와 traceback 이 몇 번
남았는지도 본다(:func:`keepalive_request`).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx
import pytest

from tests.e2e.conftest import (
    BASE_URL,
    PORTS,
    USER_PASSWORD,
    AdminClient,
    Stack,
    bearer,
    keepalive_request,
    login,
    register_and_login,
    unique,
    wait_for,
)
from tests.e2e.ledger import OBSERVATIONS, covers
from tests.e2e.test_l3_scenarios import celery_client

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(600)]

#: 처리되지 않은 예외 한 건이 남기는 기록 — 앱 핸들러의 ERROR 와 uvicorn 의 ASGI 예외 줄.
UNHANDLED_MARKERS = ("[UnhandledException]", "Exception in ASGI application")
INTERNALS = (
    "Traceback",
    "OperationalError",
    "pymysql",
    "aiomysql",
    "redis.exceptions",
    "13341",
    "13342",
    "16393",
    "SELECT ",
)


def probe(stack: Stack, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """요청 하나의 결과 — 상태·본문·연결 종료 여부·그 사이 남은 처리되지 않은 예외 기록 수."""
    mark = len(stack.app_output())
    status, body, closed, _ = keepalive_request(method, path, **kwargs)
    time.sleep(0.5)
    logged = stack.app_output()[mark:]
    return {
        "status": status,
        "body": body.decode("utf-8", "replace"),
        "closed": closed,
        "unhandled": sum(logged.count(m) for m in UNHANDLED_MARKERS),
        "redis_unavailable": logged.count("[RedisUnavailable]"),
        "tracebacks": logged.count("Traceback (most recent call last)"),
    }


def form(data: dict[str, str]) -> dict[str, Any]:
    from urllib.parse import urlencode

    return {
        "headers": {"Content-Type": "application/x-www-form-urlencoded"},
        "body": urlencode(data).encode(),
    }


def as_json(payload: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    headers = {"Content-Type": "application/json", **(bearer(token) if token else {})}
    return {"headers": headers, "body": json.dumps(payload).encode()}


# ── Redis ─────────────────────────────────────────────────────────────────
def test_redis_outage_and_recovery(stack: Stack, superuser):
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        user = register_and_login(api)
        victim = register_and_login(api)
    admin = AdminClient()
    assert admin.login(superuser["username"]).status_code == 302
    stack.compose("stop", "redis")
    try:
        assert probe(stack, "GET", "/ready")["status"] == 503
        assert probe(stack, "GET", "/health")["status"] == 200
        public = probe(stack, "GET", "/api/v1/blog/posts")
        assert (
            public["status"] == 200 and not public["closed"]
        ), "Redis 를 쓰지 않는 경로는 영향이 없다"

        # 관리 화면 — 세션을 읽지 못하면 앱에 닿지 않는다(fail-closed 503), 사용자 변경도 저장되지 않는다.
        assert admin.request("GET", "/admin/").status_code == 503
        edited = admin.request(
            "POST",
            f"/admin/user/edit/{victim['id']}",
            data={"username": victim["username"], "email": "x@example.com"},
        )
        assert edited.status_code == 503
        assert (
            stack.sql("SELECT is_active FROM users WHERE id=%s", (victim["id"],))[0]["is_active"]
            == 1
        )

        # Redis 를 필수로 쓰는 API 경로 — 503 SERVICE_UNAVAILABLE, 정상 HTTP 응답(keep-alive 유지), 기록 한 번
        # (사용자 결정 1 · F-004). 가입·로그인(레이트 리밋)·refresh(회전 기록)·비활성화(세션 폐기).
        results = {
            "login": probe(
                stack,
                "POST",
                "/api/v1/auth/login",
                **form({"username": user["username"], "password": USER_PASSWORD}),
            ),
            "refresh": probe(
                stack, "POST", "/api/v1/auth/refresh", **as_json({"refresh_token": user["refresh"]})
            ),
            "register": probe(
                stack,
                "POST",
                "/api/v1/auth/register",
                **as_json(
                    {
                        "username": unique("r"),
                        "email": f"{unique('r')}@example.com",
                        "password": USER_PASSWORD,
                    }
                ),
            ),
            "deactivate": probe(
                stack,
                "PATCH",
                f"/api/v1/user/users/{victim['id']}",
                **as_json({"is_active": False}, superuser["access"]),
            ),
        }
        for name, result in results.items():
            assert result["status"] == 503, (name, result)
            assert json.loads(result["body"])["error_code"] == "SERVICE_UNAVAILABLE", (
                name,
                result["body"],
            )
            assert not any(word in result["body"] for word in INTERNALS), (name, result["body"])
            assert not result["closed"], f"{name}: keep-alive 연결이 끊겼다"
            assert result["unhandled"] == 0 and result["redis_unavailable"] == 1, (name, result)

        # 관리 화면, 쿠키 없는 첫 요청 — 세션 **저장**(응답 직전)이 실패하면 현행 500(문서화된 동작, 정책 결정 대상).
        anonymous = probe(stack, "GET", "/admin/login")
        assert anonymous["status"] == 500, anonymous
        _record_unhandled({"admin-anonymous": anonymous})
        # fail-closed — 폐기(Redis)가 실패하면 비활성화 커밋도 하지 않는다.
        assert (
            stack.sql("SELECT is_active FROM users WHERE id=%s", (victim["id"],))[0]["is_active"]
            == 1
        )
    finally:
        stack.compose("start", "redis")
    wait_for(
        lambda: httpx.get(f"{BASE_URL}/ready", timeout=5).status_code == 200,
        60,
        "Redis 재기동 뒤 /ready 가 회복되지 않았다",
    )
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        assert login(api, user["username"])["access"]
    fresh = AdminClient()
    try:
        assert fresh.login(superuser["username"]).status_code == 302 and fresh.is_logged_in()
    finally:
        fresh.close()
        admin.close()
    covers("fault", "Redis 정지", "Redis 재기동")


def _record_unhandled(results: dict[str, dict[str, Any]]) -> None:
    doubled = sorted(n for n, r in results.items() if r["unhandled"] >= 2)
    closed = sorted(n for n, r in results.items() if r["closed"])
    if doubled or closed:
        OBSERVATIONS.add(
            f"Redis 장애 500 경로({', '.join(sorted(results))}) — 처리되지 않은 예외 기록 2건 이상: "
            f"{', '.join(doubled) or '없음'}, keep-alive 연결 끊김: {', '.join(closed) or '없음'}"
        )


# ── MySQL primary ─────────────────────────────────────────────────────────
def test_primary_outage_and_recovery(stack: Stack):
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        user = register_and_login(api)
    stack.sql("SET GLOBAL offline_mode = ON", root=True)
    try:
        assert probe(stack, "GET", "/ready")["status"] == 503
        assert probe(stack, "GET", "/health")["status"] == 200
        write = probe(
            stack,
            "POST",
            "/api/v1/blog/posts",
            **as_json({"title": "t", "content": "c"}, user["access"]),
        )
        assert write["status"] == 500 and not write["closed"], write
        assert json.loads(write["body"])["error_code"] == "DATABASE_ERROR"
        assert not any(word in write["body"] for word in INTERNALS), write["body"]
        assert write["unhandled"] == 0, "DB 오류는 변환기가 처리한다"
    finally:
        stack.sql("SET GLOBAL offline_mode = OFF", root=True)
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        wait_for(
            lambda: api.post(
                "/api/v1/blog/posts",
                json={"title": "t", "content": "c"},
                headers=bearer(user["access"]),
            ).status_code
            == 201,
            30,
            "primary 회복 뒤 쓰기가 돌아오지 않았다",
        )
        assert api.get("/ready").status_code == 200
    covers("fault", "primary 정지")


# ── MySQL replica ─────────────────────────────────────────────────────────
def test_replica_outage(stack: Stack):
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        user = register_and_login(api)
    stack.sql("SET GLOBAL offline_mode = ON", target="replica", root=True)
    try:
        # replica 연결 오류 → primary 로 한 번 다시 읽는다(사용자 결정 2 · F-005). 정상 응답·연결 유지·WARNING 한 줄.
        mark = len(stack.app_output())
        read = probe(stack, "GET", "/api/v1/blog/posts")
        assert read["status"] == 200 and not read["closed"] and read["unhandled"] == 0, read
        logged = stack.app_output()[mark:]
        assert "[DBRouter] replica 연결 오류 — primary 로 다시 읽는다" in logged
        assert "WARNING" in next(line for line in logged.splitlines() if "[DBRouter]" in line)
        assert not any(
            word in logged for word in (stack.secrets["E2E_MYSQL_PASSWORD"], "fastapi_passive_e2e:")
        )
        me = probe(stack, "GET", "/api/v1/auth/me", headers=bearer(user["access"]))
        assert me["status"] == 200, "읽기 전용 세션의 인증 읽기도 primary 로 넘어간다"
        write = probe(
            stack,
            "POST",
            "/api/v1/blog/posts",
            **as_json({"title": "w", "content": "c"}, user["access"]),
        )
        assert write["status"] == 201, "쓰기는 primary 라 영향이 없다"
        assert probe(stack, "GET", "/ready")["status"] == 200, "/ready 는 writer 만 본다(정책 유지)"
    finally:
        stack.sql("SET GLOBAL offline_mode = OFF", target="replica", root=True)
    wait_for(
        lambda: httpx.get(f"{BASE_URL}/api/v1/blog/posts", timeout=5).status_code == 200,
        30,
        "replica 회복 뒤 읽기가 돌아오지 않았다",
    )
    covers("fault", "replica 정지")


# ── Celery worker ─────────────────────────────────────────────────────────
def test_worker_outage_does_not_touch_the_api_and_queued_tasks_run_after_restart(stack: Stack):
    stack.stop_worker()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=30) as api:
            user = register_and_login(api)
            assert (
                api.post(
                    "/api/v1/blog/posts",
                    json={"title": "w", "content": "c"},
                    headers=bearer(user["access"]),
                ).status_code
                == 201
            )
            assert api.get("/ready").status_code == 200
        pending = celery_client().send_task("home.aggregate_access_stats")
        time.sleep(3)
        assert not pending.ready(), "워커가 없는데 처리됐다"
    finally:
        stack.start_worker()
    assert pending.get(timeout=60)["total"] >= 0
    covers("fault", "worker 정지")


# ── passive 전용: CSRF 폼 본문 버퍼링 측정(결정은 사용자) ─────────────────
def _memory(pid: int) -> tuple[int, int]:
    """(현재 RSS, 최대 RSS) 바이트."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        handle = ctypes.windll.kernel32.OpenProcess(0x0400 | 0x0010, False, pid)
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        ctypes.windll.kernel32.CloseHandle(handle)
        return counters.WorkingSetSize, counters.PeakWorkingSetSize
    status = open(f"/proc/{pid}/status", encoding="ascii").read()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    return int(fields["VmRSS"].split()[0]) * 1024, int(fields["VmHWM"].split()[0]) * 1024


def _server_pid(stack: Stack) -> int:
    """포트 18093 을 듣는 실제 서버 PID — Windows venv 의 ``python.exe`` 는 런처라 Popen PID 가 아니다."""
    assert stack.app is not None
    if os.name != "nt":
        return stack.app.pid
    import subprocess

    out = subprocess.run(
        ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, check=True
    ).stdout  # noqa: S607
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 5 and parts[1] == f"127.0.0.1:{PORTS['app']}" and parts[3] == "LISTENING":
            return int(parts[4])
    raise AssertionError("18093 을 듣는 프로세스가 없다")


def _measure(stack: Stack, pid: int, label: str, mib: int, body: bytes) -> dict[str, Any]:
    before, peak_before = _memory(pid)
    status, _, closed, elapsed = keepalive_request(
        "POST",
        "/admin/login",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )
    after, peak_after = _memory(pid)
    assert (
        httpx.get(f"{BASE_URL}/health", timeout=10).status_code == 200
    ), "큰 본문 뒤 서버가 죽었다"
    return {
        "shape": label,
        "MiB": mib,
        "status": status,
        "seconds": round(elapsed, 3),
        "rss_before_MiB": round(before / 2**20, 1),
        "rss_after_MiB": round(after / 2**20, 1),
        "peak_rss_increase_MiB": round(max(0, peak_after - peak_before) / 2**20, 1),
        "connection_closed": closed,
    }


def test_measure_csrf_form_body_buffering(stack: Stack):
    """익명 ``POST /admin/login`` 에 토큰 없는 큰 폼 본문 — CSRF 미들웨어는 본문 전체를 메모리에 읽고 파싱한다.

    상한을 둘지는 사용자 결정이다(계획서 §5-2) — 응답·시간·RSS 를 재서 기록만 한다. 두 모양으로 잰다.

    * ``fields-512KiB``: 512 KiB 필드 여러 개 — 끝까지 읽고 파싱한 뒤 토큰이 없어 403.
    * ``one-field``: 필드 하나 — Starlette 폼 파서의 필드 상한(1 MiB)을 넘으면 미들웨어 안에서 예외가 난다.
    """
    pid = _server_pid(stack)
    results = []
    for mib in (1, 10, 50):
        chunk = b"x" * (512 * 1024)
        many = b"username=a&password=b&" + b"&".join(b"f%d=" % i + chunk for i in range(mib * 2))
        results.append(_measure(stack, pid, "fields-512KiB", mib, many))
        results.append(
            _measure(
                stack, pid, "one-field", mib, b"username=a&password=b&pad=" + b"x" * (mib * 2**20)
            )
        )
    assert all(r["status"] == 403 for r in results if r["shape"] == "fields-512KiB"), results
    (stack.run_dir / "csrf-body-measure.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), "utf-8"
    )
    stack.outputs.append(stack.run_dir / "csrf-body-measure.json")
    OBSERVATIONS.add(
        f"CSRF 폼 본문 버퍼링 측정({os.name}): " + json.dumps(results, ensure_ascii=False)
    )
    covers("fault", "CSRF 본문 측정")
