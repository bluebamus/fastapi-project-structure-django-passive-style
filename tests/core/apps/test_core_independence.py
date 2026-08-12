"""NFR-06 — registry core 는 웹 프레임워크에 의존하지 않는다.

Django lifecycle(``AppConfig``/``Apps``)과 FastAPI·SQLAdmin 결선을 분리해 둔 이유는
CR-08 때문이다: 결선은 "Django 와 같은 동작" 이 아니라 이 프로젝트 전용 adapter 다.
경계가 코드에도 남아 있는지 import 로 확인한다.

부수 효과 하나가 더 있다 — ``ADMIN=False`` 에서 sqladmin 이 registry 결선 때문에
eager-load 되지 않는다는 SEC-01 의 전제가 여기서부터 성립한다.
"""

import subprocess  # noqa: S404 - 깨끗한 인터프리터에서 import 그래프를 관찰한다
import sys

PROBE = """
import importlib
import json
import sys

for name in ("app.core.apps", "app.core.apps.config", "app.core.apps.registry"):
    importlib.import_module(name)

banned = sorted(m for m in sys.modules if m.split(".")[0] in {"fastapi", "sqladmin", "starlette"})
print("__RESULT__" + json.dumps(banned))
"""


def test_registry_core_imports_no_web_framework():
    """registry core 만 import 했을 때 fastapi/sqladmin 이 딸려오면 안 된다."""
    proc = subprocess.run(  # noqa: S603 - 인터프리터·스크립트가 이 파일에 고정돼 있다
        [sys.executable, "-c", PROBE],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    line = next(x for x in proc.stdout.splitlines() if x.startswith("__RESULT__"))
    loaded = line.removeprefix("__RESULT__")
    assert loaded == "[]", f"registry core 가 웹 프레임워크를 끌어들였다: {loaded}"
