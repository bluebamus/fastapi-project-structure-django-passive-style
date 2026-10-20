"""전수 통합(e2e) 하네스 — 실제 MySQL 복제·Redis·uvicorn·Celery worker 위에서 돈다 (integration-e2e).

한 세션의 흐름:

1. **대상 검사** — 모든 DSN·Redis 의 host 가 ``127.0.0.1`` 이고 포트가 :data:`PORTS` 인지 본다.
   아니면 아무 데도 접속하지 않고 멈춘다(남의 MySQL·Redis 에 붙는 사고를 구조로 막는다).
2. ``compose.e2e.yaml`` 을 프로젝트 ``itest-passive`` 로 ``up -d --wait`` — 비밀번호는 실행마다 새로
   만든다(CI 는 미리 만들어 마스킹한 값을 ``E2E_*`` 로 준다). Windows 면 ``wsl -e docker`` 를 쓰고
   비밀번호는 ``WSLENV`` 로 넘긴다 — 파일에 적지 않는다(CRLF 의 ``\\r`` 이 섞이지 않게).
3. Alembic ``upgrade head``(primary) → replica 에 복제됐는지 확인.
4. uvicorn(``:18093``)과 Celery worker 를 **``.env`` 가 없는 실행 디렉터리**에서 띄운다. 설정은 전부
   환경 변수로 준다 — 저장소의 ``.env`` 가 접속 대상·홉 수 같은 값을 바꾸지 못한다.
5. 끝나면 프로세스를 내리고 ``compose down``(``-v`` 없음 — 데이터는 tmpfs). ``E2E_KEEP_STACK=1`` 이면
   컨테이너를 남긴다. ``E2E_ARTIFACT_DIR`` 을 주면 로그를 그리로 복사한다(CI 실패 산출물).

앱은 ``ENV=production``·``DEBUG=false``·``LOG_FILE_ENABLED=true`` 로 띄운다 — 운영과 같은 설정 검증·
파일 로그·Alembic 전용 스키마 경로를 그대로 탄다.
"""

from __future__ import annotations

import contextlib
import fnmatch
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pymysql
import pytest
import redis as redis_lib

from tests.e2e.ledger import ISSUED_TOKENS, SEEN_REDIS_KEYS

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = "compose.e2e.yaml"
PROJECT = "itest-passive"
HOST = "127.0.0.1"
#: 이 저장소 전용 포트(계획서 §0). 여기 밖의 포트로는 접속하지 않는다.
PORTS = {"mysql_primary": 13341, "mysql_replica": 13342, "redis": 16393, "app": 18093}
DB_NAME = DB_USER = "fastapi_passive_e2e"
BASE_URL = f"http://{HOST}:{PORTS['app']}"

#: 자식 프로세스에 그대로 넘길 OS 변수 — 나머지(셸에 남은 설정 변수 등)는 넘기지 않는다.
_OS_ENV_ALLOW = (
    "PATH",
    "PATHEXT",
    "SYSTEMROOT",
    "SystemRoot",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "TEMP",
    "TMP",
    "TMPDIR",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
    "LANG",
    "LC_ALL",
    # aiomysql 은 import 시 getpass.getuser() 를 부른다 — 사용자명 변수가 없으면 OSError.
    "USERNAME",
    "USER",
    "LOGNAME",
)


def wait_for(condition: Callable[[], Any], timeout: float, what: str, interval: float = 0.2) -> Any:
    """``condition()`` 이 참을 돌려줄 때까지 기다린다(임의의 sleep 대신 조건 대기)."""
    deadline = time.monotonic() + timeout
    last: Any = None
    while time.monotonic() < deadline:
        try:
            last = condition()
            if last:
                return last
        except Exception as exc:  # noqa: BLE001 - 대기 중의 일시 오류는 다음 시도로 넘긴다
            last = exc
        time.sleep(interval)
    raise TimeoutError(f"{timeout:.0f}s 안에 {what} — 마지막 값: {last!r}")


def verify_local_targets(env: dict[str, str]) -> None:
    """앱 환경의 모든 접속 대상이 이 저장소 전용 로컬 포트인지 본다. 아니면 즉시 멈춘다."""
    replica_hosts = json.loads(env.get("MYSQL_REPLICA_HOSTS", "[]"))
    targets = {
        "MYSQL": (env.get("MYSQL_HOST"), env.get("MYSQL_PORT"), PORTS["mysql_primary"]),
        "REDIS": (env.get("REDIS_HOST"), env.get("REDIS_PORT"), PORTS["redis"]),
        **{
            f"REPLICA[{i}]": (host, env.get("MYSQL_REPLICA_PORT"), PORTS["mysql_replica"])
            for i, host in enumerate(replica_hosts)
        },
    }
    bad = [
        f"{name}={host}:{port} (허용: {HOST}:{want})"
        for name, (host, port, want) in targets.items()
        if host != HOST or str(port) != str(want)
    ]
    if bad:
        pytest.exit(
            "e2e 접속 대상이 이 저장소 전용 포트가 아니다 — " + ", ".join(bad), returncode=3
        )


class Stack:
    """한 세션의 e2e 환경 — 컨테이너·앱·워커와 그 접속 도구."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.secrets = {
            "E2E_MYSQL_ROOT_PASSWORD": os.getenv("E2E_MYSQL_ROOT_PASSWORD")
            or secrets.token_urlsafe(24),
            "E2E_MYSQL_PASSWORD": os.getenv("E2E_MYSQL_PASSWORD") or secrets.token_urlsafe(24),
            "E2E_REPL_PASSWORD": os.getenv("E2E_REPL_PASSWORD") or secrets.token_urlsafe(24),
            "ACCESS_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "REFRESH_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "SESSION_SECRET_KEY": secrets.token_urlsafe(48),
        }
        self.app: subprocess.Popen[bytes] | None = None
        self.worker: subprocess.Popen[bytes] | None = None
        self.app_overrides: dict[str, str] = {}
        self._launches = 0
        self.outputs: list[Path] = []

    # ── docker ────────────────────────────────────────────────────────────
    def compose(self, *args: str, timeout: float = 300, check: bool = True) -> str:
        """이 프로젝트(``itest-passive``)에만 compose 명령을 보낸다."""
        docker = ["wsl", "-e", "docker"] if os.name == "nt" else ["docker"]
        names = [n for n in self.secrets if n.startswith("E2E_")]
        env = {**os.environ, **{n: self.secrets[n] for n in names}}
        if os.name == "nt":
            env["WSLENV"] = ":".join([*names, *filter(None, [os.getenv("WSLENV")])])
        proc = subprocess.run(  # noqa: S603 - 고정된 docker 명령
            [*docker, "compose", "-p", PROJECT, "-f", COMPOSE_FILE, *args],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if check and proc.returncode != 0:
            raise RuntimeError(
                f"compose {' '.join(args)} 실패({proc.returncode}):\n{proc.stderr[-3000:]}"
            )
        return proc.stdout + proc.stderr

    # ── DB·Redis 접속 ────────────────────────────────────────────────────
    def db(self, target: str = "primary", *, root: bool = False) -> pymysql.connections.Connection:
        port = PORTS["mysql_primary" if target == "primary" else "mysql_replica"]
        return pymysql.connect(
            host=HOST,
            port=port,
            user="root" if root else DB_USER,
            password=self.secrets["E2E_MYSQL_ROOT_PASSWORD" if root else "E2E_MYSQL_PASSWORD"],
            database=DB_NAME,
            autocommit=True,
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor,
        )

    def sql(self, query: str, args: Any = None, *, target: str = "primary", root: bool = False):
        with contextlib.closing(self.db(target, root=root)) as conn, conn.cursor() as cur:
            cur.execute(query, args)
            return cur.fetchall()

    def redis(self) -> redis_lib.Redis:
        return redis_lib.Redis(host=HOST, port=PORTS["redis"], decode_responses=True)

    def snapshot_redis_keys(self) -> set[str]:
        with contextlib.suppress(redis_lib.RedisError):
            keys = set(self.redis().scan_iter(count=1000))
            SEEN_REDIS_KEYS.update(keys)
            return keys
        return set()

    def wait_replicated(self, table: str, where: str, args: Any, timeout: float = 15) -> None:
        wait_for(
            lambda: self.sql(f"SELECT 1 FROM {table} WHERE {where}", args, target="replica"),  # noqa: S608
            timeout,
            f"replica 에 {table} 행이 복제되지 않았다",
        )

    # ── 앱·워커 ──────────────────────────────────────────────────────────
    def app_env(self, **overrides: str) -> dict[str, str]:
        env = {name: os.environ[name] for name in _OS_ENV_ALLOW if name in os.environ}
        env.update(
            {
                "ENV": "production",
                "DEBUG": "false",
                "LOG_FILE_ENABLED": "true",
                "LOG_CONSOLE_ENABLED": "true",
                "LOG_DIR": str(self.run_dir / "logs"),
                "MYSQL_HOST": HOST,
                "MYSQL_PORT": str(PORTS["mysql_primary"]),
                "MYSQL_USER": DB_USER,
                "MYSQL_PASSWORD": self.secrets["E2E_MYSQL_PASSWORD"],
                "MYSQL_DATABASE": DB_NAME,
                "DB_ROUTER_ENABLED": "true",
                "DB_REPLICATION_ENABLED": "true",
                "MYSQL_REPLICA_HOSTS": json.dumps([HOST]),
                "MYSQL_REPLICA_PORT": str(PORTS["mysql_replica"]),
                "REDIS_HOST": HOST,
                "REDIS_PORT": str(PORTS["redis"]),
                "REDIS_PASSWORD": "",
                "REDIS_DB": "0",
                "ACCESS_TOKEN_SECRET_KEY": self.secrets["ACCESS_TOKEN_SECRET_KEY"],
                "REFRESH_TOKEN_SECRET_KEY": self.secrets["REFRESH_TOKEN_SECRET_KEY"],
                "SESSION_SECRET_KEY": self.secrets["SESSION_SECRET_KEY"],
                # 홉 수는 여기서 고정한다 — 저장소 .env 의 값이 결과를 바꾸지 못하게.
                "TRUSTED_PROXY_HOPS": "0",
                # 레이트 리밋은 그 시나리오(L3-2·L4-1)만 좁혀서 다시 띄운다.
                "AUTH_LOGIN_MAX_ATTEMPTS": "1000",
                "AUTH_LOGIN_IP_MAX_ATTEMPTS": "1000",
                "AUTH_REGISTER_MAX_ATTEMPTS": "1000",
                "PYTHONPATH": str(REPO_ROOT),
                "PYTHONIOENCODING": "utf-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        env.update(overrides)
        verify_local_targets(env)
        return env

    def run_python(self, *args: str, input: str | None = None, timeout: float = 180, **env: str):
        """저장소 코드를 ``.env`` 없는 실행 디렉터리에서 한 번 돌린다(스크립트·Alembic)."""
        launcher = [sys.executable, "-X", "utf8"]
        return subprocess.run(  # noqa: S603 - 인터프리터 고정
            [*launcher, *args],
            cwd=self.run_dir,
            env=self.app_env(**env),
            input=input,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )

    def _output(self, name: str) -> Any:
        self._launches += 1
        path = self.run_dir / f"{self._launches:02d}-{name}.out"
        self.outputs.append(path)
        return path.open("wb")

    def start_app(self, **overrides: str) -> None:
        self.stop_app()
        self.app_overrides = dict(overrides)
        launcher = [sys.executable, "-X", "utf8", "-m", "uvicorn"]
        args = ["main:app", "--host", HOST, "--port", str(PORTS["app"])]
        self.app = subprocess.Popen(  # noqa: S603 - 인터프리터 고정
            [*launcher, *args],
            cwd=self.run_dir,
            env=self.app_env(**overrides),
            stdout=self._output("uvicorn"),
            stderr=subprocess.STDOUT,
        )

        def serving() -> bool:
            if self.app is not None and self.app.poll() is not None:
                raise RuntimeError(
                    f"uvicorn 이 기동 중 종료했다({self.app.returncode}): {self.tail()}"
                )
            return httpx.get(f"{BASE_URL}/health", timeout=2).status_code == 200

        try:
            wait_for(serving, 60, "uvicorn 이 /health 200 을 내지 않았다")
        except RuntimeError:
            raise
        except TimeoutError as exc:
            raise TimeoutError(f"{exc}\n{self.tail()}") from exc

    def stop_app(self) -> None:
        self._stop(self.app)
        self.app = None

    def start_worker(self, **overrides: str) -> None:
        self.stop_worker()
        # Windows 는 prefork 를 못 쓴다 — solo. Linux(CI)는 운영과 같은 prefork 1개.
        pool = ["--pool=solo"] if os.name == "nt" else ["--pool=prefork", "--concurrency=1"]
        launcher = [sys.executable, "-X", "utf8", "-m", "celery"]
        out = self._output("celery")
        path = self.outputs[-1]
        self.worker = subprocess.Popen(  # noqa: S603 - 인터프리터 고정
            [*launcher, "-A", "app.celery.app", "worker", "--loglevel=INFO", *pool],
            cwd=self.run_dir,
            env=self.app_env(**overrides),
            stdout=out,
            stderr=subprocess.STDOUT,
        )
        wait_for(
            lambda: b" ready." in path.read_bytes()
            or (self.worker is not None and self.worker.poll() is not None),
            90,
            "Celery worker 가 ready 를 남기지 않았다",
        )
        if self.worker.poll() is not None:
            raise RuntimeError(
                f"Celery worker 가 기동 중 종료했다: {path.read_text('utf-8', 'replace')[-3000:]}"
            )

    def stop_worker(self) -> None:
        self._stop(self.worker, grace=20)
        self.worker = None

    @staticmethod
    def _stop(proc: subprocess.Popen[bytes] | None, grace: float = 15) -> None:
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    def tail(self, lines: int = 40) -> str:
        if not self.outputs:
            return ""
        text = self.outputs[-1].read_text("utf-8", "replace") if self.outputs[-1].exists() else ""
        return "\n".join(text.splitlines()[-lines:])

    def log_files(self) -> list[Path]:
        return [*self.outputs, *sorted((self.run_dir / "logs").glob("*.log*"))]

    def all_logs(self) -> str:
        return "\n".join(p.read_text("utf-8", "replace") for p in self.log_files() if p.is_file())

    def logs_since(self, mark: int) -> str:
        """``mark = len(stack.all_logs())`` 이후에 쌓인 앱 출력(현재 uvicorn 출력 파일 기준)."""
        return self.app_output()[mark:]

    def app_output(self) -> str:
        uvicorn = [p for p in self.outputs if p.name.endswith("-uvicorn.out")]
        return uvicorn[-1].read_text("utf-8", "replace") if uvicorn else ""

    # ── 사용자 ───────────────────────────────────────────────────────────
    def create_superuser(self, username: str, password: str, *, set_password: bool = False):
        args = ["-m", "scripts.create_superuser", "--username", username, "--password-stdin"]
        args += ["--set-password"] if set_password else ["--email", f"{username}@example.com"]
        return self.run_python(*args, input=f"{password}\n")


def _collect_artifacts(stack: Stack) -> None:
    target = os.getenv("E2E_ARTIFACT_DIR")
    if not target:
        return
    dest = Path(target)
    dest.mkdir(parents=True, exist_ok=True)
    for path in stack.log_files():
        if path.is_file():
            shutil.copy2(path, dest / path.name)
    for service in ("mysql-primary", "mysql-replica", "redis"):
        out = stack.compose("logs", "--no-color", service, check=False)
        (dest / f"compose-{service}.log").write_text(out, encoding="utf-8")


@pytest.fixture(scope="session")
def stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Stack]:
    run_dir = tmp_path_factory.mktemp("e2e-run")
    (run_dir / "logs").mkdir()
    instance = Stack(run_dir)
    instance.app_env()  # 대상 검사 — 어떤 접속보다 먼저
    try:
        instance.compose("up", "-d", "--wait", "--force-recreate", timeout=600)
        migrated = instance.run_python(
            "-m", "alembic", "-c", str(REPO_ROOT / "alembic.ini"), "upgrade", "head"
        )
        assert migrated.returncode == 0, migrated.stderr[-3000:]
        (run_dir / "alembic-upgrade.out").write_text(migrated.stdout + migrated.stderr, "utf-8")
        instance.outputs.append(run_dir / "alembic-upgrade.out")
        instance.wait_replicated(
            "information_schema.tables", "table_schema=%s AND table_name=%s", (DB_NAME, "users")
        )
        instance.start_app()
        instance.start_worker()
        yield instance
    finally:
        instance.stop_worker()
        instance.stop_app()
        with contextlib.suppress(Exception):
            _collect_artifacts(instance)
        if os.getenv("E2E_KEEP_STACK") != "1":
            instance.compose("down", check=False)


@pytest.fixture(autouse=True)
def _observe_redis(stack: Stack) -> Iterator[None]:
    """테스트마다 끝에서 Redis 키를 관찰한다(인벤토리의 Redis 접두어 대조)."""
    yield
    stack.snapshot_redis_keys()


@pytest.fixture
def api(stack: Stack) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        yield client


def bearer(token: str) -> dict[str, str]:
    ISSUED_TOKENS.add(token)
    return {"Authorization": f"Bearer {token}"}


def unique(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(5)}"


#: 테스트 사용자 비밀번호 — 실행마다 다르다(로그 비밀값 검사 대상).
USER_PASSWORD = "Pw-" + secrets.token_urlsafe(12)


def register_and_login(api: httpx.Client, username: str | None = None) -> dict[str, str]:
    """가입 → 로그인. ``{"username", "id", "access", "refresh"}``."""
    username = username or unique("user")
    created = api.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": USER_PASSWORD},
    )
    assert created.status_code == 201, created.text
    tokens = login(api, username)
    me = api.get("/api/v1/auth/me", headers=bearer(tokens["access"]))
    assert me.status_code == 200, me.text
    return {"username": username, "id": me.json()["id"], **tokens}


def login(api: httpx.Client, username: str, password: str = USER_PASSWORD) -> dict[str, str]:
    response = api.post("/api/v1/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    ISSUED_TOKENS.update({body["access_token"], body["refresh_token"]})
    return {"access": body["access_token"], "refresh": body["refresh_token"]}


@pytest.fixture(scope="session")
def superuser(stack: Stack) -> dict[str, str]:
    """``scripts.create_superuser`` 로 만든 슈퍼유저와 그 토큰."""
    username = unique("admin")
    made = stack.create_superuser(username, USER_PASSWORD)
    assert made.returncode == 0, made.stderr[-2000:]
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        tokens = login(client, username)
        me = client.get("/api/v1/auth/me", headers=bearer(tokens["access"])).json()
    return {"username": username, "id": me["id"], **tokens}


def glob_match(patterns: set[str], key: str) -> set[str]:
    return {p for p in patterns if fnmatch.fnmatchcase(key, p)}


class AdminClient:
    """브라우저 없이 관리 화면을 부르는 클라이언트.

    앱이 ``ENV=production`` 이라 관리 세션 쿠키는 ``Secure`` 다. httpx 의 쿠키 저장소는 ``http://`` 로
    Secure 쿠키를 보내지 않으므로 ``admin_session`` 을 직접 들고 ``Cookie`` 헤더로 싣는다.
    """

    COOKIE = "admin_session"

    def __init__(self) -> None:
        self.client = httpx.Client(base_url=BASE_URL, timeout=30, follow_redirects=False)
        self.cookie: str | None = None

    def close(self) -> None:
        self.client.close()

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", None) or {})
        if self.cookie:
            headers["Cookie"] = f"{self.COOKIE}={self.cookie}"
        response = self.client.request(method, path, headers=headers, **kwargs)
        for raw in response.headers.get_list("set-cookie"):
            name, _, rest = raw.partition("=")
            if name.strip() == self.COOKIE:
                value = rest.split(";", 1)[0]
                self.cookie = value or None
                if "max-age=0" in raw.lower() or "expires=thu, 01 jan 1970" in raw.lower():
                    self.cookie = None
        return response

    def csrf(self, path: str = "/admin/login") -> str:
        import re

        page = self.request("GET", path).text
        found = re.search(r'name="csrf_token"\s+value="([^"]+)"', page) or re.search(
            r'<meta name="csrf-token" content="([^"]+)"', page
        )
        assert found, f"{path} 에 CSRF 토큰이 없다"
        return found.group(1)

    def login(self, username: str, password: str = USER_PASSWORD) -> httpx.Response:
        token = self.csrf()
        return self.request(
            "POST",
            "/admin/login",
            data={"username": username, "password": password, "csrf_token": token},
        )

    def is_logged_in(self) -> bool:
        response = self.request("GET", "/admin/")
        return response.status_code == 200


@pytest.fixture
def admin_client() -> Iterator[AdminClient]:
    client = AdminClient()
    yield client
    client.close()
