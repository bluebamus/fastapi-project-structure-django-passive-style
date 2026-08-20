"""AC-07 — ``ADMIN=False`` 면 관리 계층이 **로드조차 되지 않는다** (SEC-01).

``ADMIN=False`` 가 "라우트만 안 붙임" 이면 설정의 의미가 실제와 어긋난다. sqladmin 과
앱별 ModelView 가 전부 메모리에 올라온 채로 라우트만 없는 상태라면, sqladmin 을
선택적 의존성으로 분리할 수도 없고 공격면도 줄지 않는다.

registry 결선이 이 계약을 깨기 쉬운 지점이다 — adapter 가 module 최상단에서
``sqladmin`` 을 import 하거나, ``AppConfig`` 가 config 단계에서 ``admin.py`` 를 훑으면
설치 앱 전부의 관리 화면이 딸려 온다. 그래서 실제로 프로세스를 띄워 ``sys.modules`` 를
관찰한다 — 이 테스트 세션은 다른 테스트가 이미 admin 을 import 해 두어 같은
프로세스에서는 판별이 불가능하다.
"""

from __future__ import annotations

import json
import pathlib
import subprocess  # noqa: S404 - 깨끗한 인터프리터에서 import 그래프를 관찰한다
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

_PROBE = """
import json, os, sys

os.environ["ADMIN"] = "{admin}"
os.environ["DEBUG"] = "false"

import main

print("__RESULT__" + json.dumps({{
    "sqladmin": "sqladmin" in sys.modules,
    "feature_admin_modules": sorted(
        m for m in sys.modules
        if m.startswith("app.features.") and m.endswith(".admin")
    ),
    "admin_routes": sorted(
        p for p in (getattr(r, "path", "") for r in main.app.routes) if p.startswith("/admin")
    ),
}}))
"""


def _boot(admin: str) -> dict:
    proc = subprocess.run(  # noqa: S603 - 인터프리터·스크립트가 이 파일에 고정돼 있다
        [sys.executable, "-X", "utf8", "-c", _PROBE.format(admin=admin)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        cwd=_REPO_ROOT,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, f"ADMIN={admin} 로 앱을 띄우지 못했습니다:\n{proc.stderr[-3000:]}"
    line = next(x for x in proc.stdout.splitlines() if x.startswith("__RESULT__"))
    return json.loads(line.removeprefix("__RESULT__"))


def test_admin_layer_is_not_loaded_when_disabled():
    """SEC-01: sqladmin 과 앱별 admin 모듈이 sys.modules 에 없다."""
    result = _boot("false")

    assert result["sqladmin"] is False, (
        "ADMIN=false 인데 sqladmin 이 로드됐습니다. registry adapter 나 앱 패키지가 "
        "admin 모듈을 eager import 하고 있지 않은지 확인하세요."
    )
    assert (
        result["feature_admin_modules"] == []
    ), f"ADMIN=false 인데 앱 admin 모듈이 로드됐습니다: {result['feature_admin_modules']}"
    assert result["admin_routes"] == []


def test_admin_layer_loads_when_enabled():
    """대조군 — 위 검사가 '어차피 안 붙는 구조' 라서 통과하는 것이 아님을 보인다."""
    result = _boot("true")

    assert result["sqladmin"] is True
    assert result["feature_admin_modules"], "ADMIN=true 인데 앱 admin 모듈이 로드되지 않았다"
    assert "/admin" in result["admin_routes"]
