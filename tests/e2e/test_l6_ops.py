"""L6 — 운영·기동: Alembic 왕복, create_superuser, 기동 거부, 로그(경로·파일·회전·레벨)."""

from __future__ import annotations

import re
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from tests.e2e.conftest import (
    BASE_URL,
    DB_NAME,
    HOST,
    PORTS,
    REPO_ROOT,
    USER_PASSWORD,
    AdminClient,
    Stack,
    bearer,
    login,
    unique,
    wait_for,
)
from tests.e2e.ledger import ISSUED_TOKENS, OBSERVATIONS, covers

pytestmark = [pytest.mark.e2e, pytest.mark.timeout(600)]

LINE = re.compile(
    r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC\] (DEBUG|INFO|WARNING|ERROR|CRITICAL)\s* \[app=[^\]]+\] \[[^\]]+\] "
)


# ── 1. Alembic 왕복 ───────────────────────────────────────────────────────
def _schema(stack: Stack, db: str) -> dict[str, list]:
    columns = stack.sql(
        "SELECT table_name, column_name, column_type, is_nullable, column_default "
        "FROM information_schema.columns WHERE table_schema=%s ORDER BY table_name, ordinal_position",
        (db,),
        root=True,
    )
    indexes = stack.sql(
        "SELECT table_name, index_name, non_unique, column_name, seq_in_index FROM information_schema.statistics "
        "WHERE table_schema=%s ORDER BY table_name, index_name, seq_in_index",
        (db,),
        root=True,
    )
    return {
        "columns": [tuple(r.values()) for r in columns],
        "indexes": [tuple(r.values()) for r in indexes],
    }


def test_alembic_upgrade_downgrade_base_upgrade_round_trip(stack: Stack):
    """primary 안의 전용 DB 에서 — 앱이 쓰는 스키마를 건드리지 않는다."""
    db = f"{DB_NAME}_alembic"
    stack.sql(f"DROP DATABASE IF EXISTS {db}", root=True)
    stack.sql(f"CREATE DATABASE {db} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci", root=True)
    stack.sql(f"GRANT ALL ON {db}.* TO '{DB_NAME}'@'%'", root=True)
    env = {"MYSQL_DATABASE": db}
    ini = str(REPO_ROOT / "alembic.ini")

    def alembic(*args: str) -> str:
        done = stack.run_python("-m", "alembic", "-c", ini, *args, **env)
        assert done.returncode == 0, done.stderr[-3000:]
        return done.stdout + done.stderr

    try:
        alembic("upgrade", "head")
        first = _schema(stack, db)
        assert first["columns"], "upgrade 뒤 테이블이 없다"
        alembic("check")  # 모델과 마이그레이션이 어긋나지 않는다(MySQL 방언으로)
        alembic("downgrade", "base")
        left = stack.sql(
            "SELECT table_name AS t FROM information_schema.tables WHERE table_schema=%s",
            (db,),
            root=True,
        )
        assert [r["t"] for r in left] == ["alembic_version"]
        alembic("upgrade", "head")
        assert _schema(stack, db) == first, "왕복 뒤 스키마가 다르다"
    finally:
        stack.sql(f"DROP DATABASE IF EXISTS {db}", root=True)
    covers("ops", "Alembic 왕복")


# ── 2. create_superuser ───────────────────────────────────────────────────
def test_create_superuser_create_duplicate_and_set_password_revokes(
    stack: Stack, api: httpx.Client
):
    name = unique("su")
    made = stack.create_superuser(name, USER_PASSWORD)
    assert made.returncode == 0 and "만들었습니다" in made.stdout, made.stderr
    again = stack.create_superuser(name, USER_PASSWORD)
    assert (
        again.returncode == 0 and "승격했습니다" in again.stdout and "비밀번호" not in again.stdout
    )
    assert stack.sql("SELECT COUNT(*) AS n FROM users WHERE username=%s", (name,))[0]["n"] == 1

    tokens = login(api, name)
    admin = AdminClient()
    try:
        assert admin.login(name).status_code == 302 and admin.is_logged_in()
        new_password = "Pw-new-" + unique("x")
        ISSUED_TOKENS.add(new_password)
        changed = stack.create_superuser(name, new_password, set_password=True)
        assert changed.returncode == 0 and "비밀번호도 바꿨습니다" in changed.stdout, changed.stderr
        assert (
            api.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh"]}).status_code
            == 401
        )
        assert not admin.is_logged_in(), "비밀번호를 바꿨는데 관리 세션이 살아 있다"
        assert (
            api.post(
                "/api/v1/auth/login", data={"username": name, "password": USER_PASSWORD}
            ).status_code
            == 401
        )
        assert login(api, name, new_password)["access"]
    finally:
        admin.close()
    OBSERVATIONS.add(
        "create_superuser --set-password: 기존 refresh family 와 관리 세션을 폐기한다(실측 — 둘 다 즉시 무효)"
    )
    covers(
        "ops",
        "create_superuser 생성",
        "create_superuser 중복",
        "create_superuser 비밀번호·세션 폐기",
    )


def test_create_superuser_rejects_bad_input(stack: Stack):
    assert stack.create_superuser("x" * 101, USER_PASSWORD).returncode == 1
    short = stack.run_python(
        "-m",
        "scripts.create_superuser",
        "--username",
        unique("s"),
        "--email",
        "s@example.com",
        "--password-stdin",
        input="short\n",
    )
    assert short.returncode == 1 and "비밀번호는" in short.stderr
    covers("ops", "create_superuser 입력 거부")


# ── 3. 기동 거부 ──────────────────────────────────────────────────────────
def _boot(stack: Stack, **env: str) -> tuple[int, str]:
    """uvicorn 을 띄워 기동이 거부되는지 본다 — (종료 코드, 출력)."""
    stack.stop_app()
    launcher = [sys.executable, "-X", "utf8", "-m", "uvicorn"]
    proc = subprocess.run(  # noqa: S603 - 인터프리터 고정
        [*launcher, "main:app", "--host", HOST, "--port", str(PORTS["app"])],
        cwd=stack.run_dir,
        env=stack.app_env(**env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
        check=False,
    )
    return proc.returncode, proc.stdout + proc.stderr


@pytest.fixture
def restore_app(stack: Stack) -> Iterator[None]:
    yield
    stack.start_app()


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"ADMIN": "false"}, "ADMIN_DISABLED"),
        (
            {"ADMIN_SESSION_IDLE_SECONDS": "7200", "ADMIN_SESSION_MAX_AGE_SECONDS": "3600"},
            "ADMIN_SESSION_IDLE_SECONDS",
        ),
        ({"ADMIN_SESSION_IDLE_SECONDS": "10"}, "ADMIN_SESSION_IDLE_SECONDS"),
        ({"ACCESS_TOKEN_SECRET_KEY": "your-secret"}, "ACCESS_TOKEN_SECRET_KEY"),
    ],
    ids=["legacy-ADMIN", "session-idle-gt-max", "session-idle-too-small", "placeholder-secret"],
)
def test_bad_settings_refuse_to_boot(stack: Stack, restore_app, env, expected):
    code, output = _boot(stack, **env)
    assert code != 0 and expected in output, output[-2000:]
    assert "Uvicorn running" not in output
    covers("ops", f"기동 거부:{next(iter(env))}")


def test_redis_older_than_7_refuses_to_boot(stack: Stack, restore_app):
    """실제 Redis 6.2(compose profile ``redis-old``)를 같은 포트로 바꿔 끼우고 기동해 본다."""
    stack.compose("stop", "redis")
    try:
        stack.compose("--profile", "redis-old", "up", "-d", "--wait", "redis-old")
        try:
            code, output = _boot(stack)
        finally:
            stack.compose("--profile", "redis-old", "stop", "redis-old")
    finally:
        stack.compose("start", "redis")
        wait_for(lambda: stack.redis().ping(), 30, "Redis 가 다시 뜨지 않았다")
    assert code != 0 and "6.2" in output and "7.0" in output, output[-2000:]
    covers("ops", "기동 거부:Redis 버전")


def test_undeclared_access_route_refuses_to_boot(stack: Stack):
    """설치 앱에 접근 수준을 선언하지 않은 라우트가 있으면 조립(create_app)이 멈춘다."""
    pkg = stack.run_dir / "e2eprobe"
    (pkg / "api" / "routers").mkdir(parents=True, exist_ok=True)
    for init in (pkg, pkg / "api", pkg / "api" / "routers"):
        (init / "__init__.py").write_text("", "utf-8")
    (pkg / "apps.py").write_text(
        "from app.core.apps import AppConfig\n\n\nclass E2eprobeConfig(AppConfig):\n    name = 'e2eprobe'\n",
        "utf-8",
    )
    (pkg / "api" / "routers" / "router.py").write_text(
        "from fastapi import APIRouter\n\ne2eprobe_router = APIRouter()\n\n\n"
        "@e2eprobe_router.get('/open')\nasync def open_view():\n    return {}\n",
        "utf-8",
    )
    code = (
        "from app.core.bootstrap import create_app\nfrom config import INSTALLED_APPS\n"
        "create_app([*INSTALLED_APPS, 'e2eprobe.apps.E2eprobeConfig'])\n"
    )
    done = stack.run_python("-c", code)
    assert done.returncode != 0, done.stdout
    assert (
        "접근 수준 정책 위반" in done.stderr
        and "GET /api/open: 접근 수준 선언이 없다" in done.stderr
    ), done.stderr[-2000:]
    covers("ops", "기동 거부:접근 정책 미선언")


# ── 4. 로그 — 실행 경로·프로세스별 파일·형식·회전·레벨 ───────────────────
def _formatted(text: str) -> list[str]:
    return [line for line in text.splitlines() if LINE.match(line)]


def _missing_from(stdout: Path, log_file: Path) -> list[str]:
    in_file = set(log_file.read_text("utf-8").splitlines())
    return [
        line for line in _formatted(stdout.read_text("utf-8", "replace")) if line not in in_file
    ]


def test_every_entry_path_logs_the_same_format_into_its_own_file(stack: Stack):
    """uvicorn CLI·``python main.py``·Celery worker·beat — 콘솔 줄이 모두 같은 형식이고, 그 줄이 전부
    자기 프로세스 파일(app.log·celery.log·celery-beat.log)에 있다(기동 초기 줄 포함)."""
    logs = stack.run_dir / "logs"
    outputs = {p.name: p for p in stack.outputs}
    uvicorn_out = next(p for n, p in outputs.items() if n.endswith("-uvicorn.out"))
    celery_out = next(p for n, p in outputs.items() if n.endswith("-celery.out"))

    # python main.py — 같은 dictConfig 를 uvicorn.run(log_config=...) 로 준다.
    stack.stop_app()
    main_out = stack.run_dir / "python-main.out"
    with main_out.open("wb") as sink:
        proc = subprocess.Popen(  # noqa: S603 - 인터프리터 고정
            [sys.executable, "-X", "utf8", str(REPO_ROOT / "main.py")],
            cwd=stack.run_dir,
            env=stack.app_env(SERVER_HOST=HOST, SERVER_PORT=str(PORTS["app"])),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
        try:
            wait_for(
                lambda: httpx.get(f"{BASE_URL}/health", timeout=2).status_code == 200,
                60,
                "python main.py 가 뜨지 않았다",
            )
            httpx.get(f"{BASE_URL}/api/v1/blog/posts?probe=python-main", timeout=10)
        finally:
            stack._stop(proc)
    stack.outputs.append(main_out)
    stack.start_app()

    beat_out = stack.run_dir / "beat.out"
    checks = {
        "uvicorn main:app": (uvicorn_out, logs / "app.log"),
        "python main.py": (main_out, logs / "app.log"),
        "celery worker": (celery_out, logs / "celery.log"),
    }
    if beat_out.exists():
        checks["celery beat"] = (beat_out, logs / "celery-beat.log")
    report = {}
    for name, (stdout, file) in checks.items():
        lines = _formatted(stdout.read_text("utf-8", "replace"))
        assert lines, f"{name}: 형식에 맞는 콘솔 줄이 없다"
        report[name] = _missing_from(stdout, file)
    assert "probe=python-main" in (logs / "app.log").read_text("utf-8")
    missing = {name: lines[:3] for name, lines in report.items() if lines}
    assert not missing, f"콘솔에는 있고 프로세스 파일에는 없는 줄: {missing}"

    # 프로세스별 파일 — 웹 파일에 워커 줄이, 워커 파일에 웹 줄이 섞이지 않는다.
    app_log = (logs / "app.log").read_text("utf-8")
    celery_log = (logs / "celery.log").read_text("utf-8")
    assert "celery@" not in app_log and "[app=uvicorn]" not in celery_log
    # 비밀값: DSN 은 계정·비밀번호가 가려져 있다.
    assert "mysql+aiomysql://***:***@127.0.0.1:13341/" in app_log
    covers("logging", "실행 경로별 형식", "프로세스별 파일", "기동 초기 줄")


def test_app_levels_filter_by_header(stack: Stack, restore_app):
    """``LOG_APP_LEVELS`` — uvicorn 헤더만 WARNING 으로 올리면 접속 줄은 사라지고 core INFO 는 남는다."""
    stack.start_app(LOG_APP_LEVELS="uvicorn=WARNING")
    marker = unique("lvl")
    httpx.get(f"{BASE_URL}/api/v1/blog/posts?probe={marker}", timeout=10)
    time.sleep(0.5)
    output = stack.app_output()
    assert marker not in output, "uvicorn=WARNING 인데 접속 줄이 남았다"
    assert "[app=core]" in output and "[startup] 자원 초기화 완료" in output
    covers("logging", "앱별 레벨")


def test_size_rotation_and_retention(stack: Stack, restore_app, superuser):
    """``LOG_MAX_SIZE_MB=1`` — 1 MiB 를 넘기면 ``app.log.<오늘>.N`` 으로 나뉘고, 보관일수를 넘긴 회전 파일은 지운다."""
    logs = stack.run_dir / "logs"
    stale = [logs / "app.log.2020-01-01", logs / "app.log.2020-01-01.1"]
    for path in stale:
        path.write_text("old\n", "utf-8")
    stack.start_app(LOG_MAX_SIZE_MB="1", LOG_RETENTION_DAYS="1")
    today = datetime.now(UTC).date().isoformat()
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        pad = "p" * 1800
        deadline = time.monotonic() + 180
        while not list(logs.glob(f"app.log.{today}.*")) and time.monotonic() < deadline:
            for _ in range(50):
                api.get(f"/api/v1/blog/posts?pad={pad}", headers=bearer(superuser["access"]))
    rotated = sorted(logs.glob(f"app.log.{today}.*"))
    assert rotated, "1 MiB 를 넘겼는데 회전 파일이 없다"
    assert all(p.stat().st_size <= 1024 * 1024 for p in rotated)
    assert not any(p.exists() for p in stale), "보관일수를 넘긴 회전 파일이 남았다"
    covers("logging", "크기 회전", "보관일수 삭제")


def test_first_db_connection_after_auth_cache_flush(stack: Stack, restore_app):
    """caching_sha2_password 인증 캐시가 빈 상태(재기동 직후·새 replica)에서도 앱의 첫 연결이 붙는다.

    캐시가 비면 전체 인증(RSA 키 교환)을 해야 하고, 그때 ``cryptography`` 가 없으면 모든 DB 요청이 500 이 된다.
    ``FLUSH PRIVILEGES`` 로 두 서버의 캐시를 비운 뒤 앱을 새로 띄워(풀도 새로) 읽기(replica)·쓰기(primary)를 한다.
    """
    stack.stop_app()
    for target in ("primary", "replica"):
        stack.sql("FLUSH LOCAL PRIVILEGES", target=target, root=True)
    stack.start_app()
    with httpx.Client(base_url=BASE_URL, timeout=30) as api:
        assert api.get("/api/v1/blog/posts").status_code == 200
        assert api.get("/ready").status_code == 200
        name = unique("cache")
        created = api.post(
            "/api/v1/auth/register",
            json={"username": name, "email": f"{name}@example.com", "password": USER_PASSWORD},
        )
        assert created.status_code == 201
    covers("ops", "인증 캐시 빈 상태 첫 연결")
