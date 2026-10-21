"""기동 초기(import 중) 로그 줄도 프로세스별 파일에 한 번씩 남는다 (integration-e2e F-006 · 사용자 결정 3 · ADR-011).

실제 프로세스를 띄워 본다 — 설정 로드 직후 첫 ``get_logger()`` 가 파일 핸들러까지 붙이므로, import 중에 나는 줄
(예: ``[database] 라우팅 구성``)이 콘솔에만 있고 파일에서 빠지는 일이 없어야 한다. 웹(``import main``)은 ``app.log``,
워커 진입(``celery … report``)은 ``celery.log`` 다. 줄이 두 번 쓰이면(핸들러 중복) 실패다.

``.env`` 가 없는 임시 디렉터리에서 환경 변수만으로 띄운다. import 만 하고 DB·Redis 에는 접속하지 않는다.
"""

from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LINE = re.compile(r"^\[\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC\] [A-Z]+\s* \[app=")


def _env(log_dir: Path) -> dict[str, str]:
    keep = (
        "PATH",
        "SYSTEMROOT",
        "SystemRoot",
        "TEMP",
        "TMP",
        "HOME",
        "USERPROFILE",
        "USERNAME",
        "USER",
        "LOGNAME",
    )
    env = {k: os.environ[k] for k in keep if k in os.environ}
    env.update(
        {
            "ENV": "production",
            "DEBUG": "false",
            "LOG_FILE_ENABLED": "true",
            "LOG_CONSOLE_ENABLED": "true",
            "LOG_DIR": str(log_dir),
            "MYSQL_HOST": "127.0.0.1",
            "MYSQL_USER": "early",
            "MYSQL_PASSWORD": secrets.token_urlsafe(16),
            "MYSQL_DATABASE": "early",
            "REDIS_HOST": "127.0.0.1",
            "REDIS_PORT": "1",
            "ACCESS_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "REFRESH_TOKEN_SECRET_KEY": secrets.token_urlsafe(48),
            "SESSION_SECRET_KEY": secrets.token_urlsafe(48),
            "PYTHONPATH": str(REPO_ROOT),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    return env


@pytest.mark.parametrize(
    ("args", "own", "other"),
    [
        (["-c", "import main"], "app.log", "celery.log"),
        (["-m", "celery", "-A", "app.celery.app", "report"], "celery.log", "app.log"),
    ],
    ids=["web-import", "celery-entry"],
)
def test_import_time_lines_land_once_in_the_process_file(tmp_path, args, own, other):
    logs = tmp_path / "logs"
    proc = subprocess.run(  # noqa: S603 - 인터프리터 고정
        [sys.executable, "-X", "utf8", *args],
        cwd=tmp_path,
        env=_env(logs),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    console = [line for line in (proc.stdout + proc.stderr).splitlines() if LINE.match(line)]
    assert any(
        "[database] 라우팅 구성" in line for line in console
    ), "import 중 줄이 콘솔에도 없다 — 검사가 헛돈다"
    in_file = Counter((logs / own).read_text("utf-8").splitlines())
    missing = [line for line in console if in_file[line] == 0]
    assert not missing, f"콘솔에는 있고 {own} 에는 없는 줄: {missing[:3]}"
    doubled = [line for line, n in in_file.items() if n > Counter(console)[line]]
    assert not doubled, f"{own} 에 두 번 쓰인 줄: {doubled[:3]}"
    assert not (logs / other).exists(), f"{other} 에 섞였다"
