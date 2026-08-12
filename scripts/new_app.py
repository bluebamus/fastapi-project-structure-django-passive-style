"""신규 기능 앱 scaffold — Django ``startapp`` 대응.

    uv run python -m scripts.new_app orders
    uv run python -m scripts.new_app orders --with-models --with-admin

생성물은 ``app/features/<name>/`` 아래의 표준 계층 골격과 ``apps.py`` 다.

**설정 파일은 건드리지 않는다.** 생성 직후 앱은 *미설치* 상태이고, 사용자가
``config.INSTALLED_APPS`` 에 출력된 config class 경로를 붙여 넣어야 Router·Models·
Admin·``ready()`` 가 활성화된다(FR-10). 생성기가 설정을 몰래 고치면 "무엇이 설치돼
있는가" 의 답이 두 곳으로 갈라진다 — 그러면 이 프로젝트의 존재 이유가 사라진다.

안전장치 두 가지(SEC-03·SEC-04):

* 경로 이탈 차단 — ``..``, 절대 경로, separator 를 거부하고, 최종 대상의 resolve
  결과가 resolve 된 ``app/features`` 하위인지 확인한다(symlink 통과 후 기준).
* 부분 생성 금지 — 임시 디렉터리에 전부 만든 뒤 성공했을 때만 최종 위치로 옮긴다.
  중간에 실패하면 임시 결과를 지우고 대상 경로는 손대지 않는다.
"""

from __future__ import annotations

import argparse
import keyword
import shutil
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FEATURES_DIR = PROJECT_ROOT / "app" / "features"


class AppScaffoldError(Exception):
    """생성기가 입력이나 대상 상태를 거부했다."""


# =============================================================================
# 이름 검증 / 경로 해석
# =============================================================================
def validate_name(name: str) -> str:
    """앱 이름이 snake_case Python identifier 인지 확인한다.

    Raises:
        AppScaffoldError: 이름이 규칙에 맞지 않거나 경로 조각을 포함한다.
    """
    if not name:
        raise AppScaffoldError("앱 이름이 비어 있습니다.")
    if any(sep in name for sep in ("/", "\\", ".", ":")):
        raise AppScaffoldError(
            f"앱 이름 '{name}' 에 경로 구분자가 있습니다. 이름만 적으세요(예: orders)."
        )
    if not name.isidentifier() or keyword.iskeyword(name):
        raise AppScaffoldError(
            f"앱 이름 '{name}' 이 유효한 Python identifier 가 아닙니다. "
            "소문자와 밑줄만 사용하세요(예: order_items)."
        )
    if name != name.lower():
        raise AppScaffoldError(f"앱 이름 '{name}' 은 snake_case 여야 합니다.")
    return name


def resolve_target(name: str, features_dir: Path = FEATURES_DIR) -> Path:
    """생성 대상 경로를 확정하고 ``app/features`` 경계 안인지 검사한다.

    이름 검사만으로는 부족하다 — ``app/features`` 자체가 symlink 이거나 그 아래에
    symlink 가 있으면 이름이 멀쩡해도 resolve 결과가 경계를 벗어날 수 있다. 그래서
    **resolve 한 뒤에** 다시 확인한다(SEC-03).
    """
    validate_name(name)
    root = features_dir.resolve()
    target = (root / name).resolve()
    if not target.is_relative_to(root):
        raise AppScaffoldError(
            f"대상 경로가 app/features 밖을 가리킵니다: {target} (기준: {root}). 생성을 중단합니다."
        )
    if target == root:
        raise AppScaffoldError("대상 경로가 app/features 자신입니다.")
    return target


# =============================================================================
# 템플릿
# =============================================================================
def _pascal(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _apps_py(name: str) -> str:
    return f'''"""{_pascal(name)} 앱 설정."""

from app.core.apps import AppConfig


class {_pascal(name)}Config(AppConfig):
    """{_pascal(name)} 기능 앱."""

    name = "app.features.{name}"
'''


def _package_init(name: str) -> str:
    return f'''"""{_pascal(name)} 기능 패키지.

가벼운 package marker 다 — Router 도 Model 도 여기서 import 하지 않는다.
결선은 ``apps.py`` 의 ``{_pascal(name)}Config`` 선언에 따라 registry 가 수행한다.
"""
'''


def _router(name: str) -> str:
    return f'''"""{_pascal(name)} 모듈 라우터 — v1 서브라우터를 취합한다.

registry adapter 가 이 모듈의 ``{name}_router`` 를 읽어 ``/api`` 에 마운트한다.
단, 앱이 ``config.INSTALLED_APPS`` 에 등록돼 있을 때만이다.
"""

from fastapi import APIRouter

from app.features.{name}.api.routers.v1 import {name} as {name}_v1

{name}_router = APIRouter()
{name}_router.include_router({name}_v1.router, prefix="/v1/{name}", tags=["{_pascal(name)}"])
'''


def _v1_view(name: str) -> str:
    return f'''"""{_pascal(name)} v1 엔드포인트."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/ping", summary="{_pascal(name)} 헬스 확인")
async def ping() -> dict[str, str]:
    """앱이 실제로 마운트됐는지 확인하는 최소 엔드포인트."""
    return {{"app": "{name}", "status": "ok"}}
'''


def _models(name: str) -> str:
    return f'''"""{_pascal(name)} 모델.

여기 정의한 모델은 앱이 등록된 경우에만 ``Base.metadata`` 와 Alembic autogenerate 에
포함된다. 새 테이블을 추가했으면 migration 을 만들고 schema 차이를 확인할 것.
"""

from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.session import Base


class {_pascal(name)}(Base):
    """{_pascal(name)} 엔티티(골격) — 실제 컬럼으로 교체하세요."""

    __tablename__ = "{name}s"

    id: Mapped[int] = mapped_column(primary_key=True)
'''


def _models_init(name: str) -> str:
    return f'''"""{_pascal(name)} 모델 공개 지점."""

from app.features.{name}.models.models import {_pascal(name)}

__all__ = ["{_pascal(name)}"]
'''


def _admin(name: str) -> str:
    return f'''"""{_pascal(name)} SQLAdmin 설정.

registry adapter 가 설치 앱의 ``admin_views`` 를 읽어 등록한다. 앱이
``config.INSTALLED_APPS`` 에 없으면 이 파일이 있어도 등록되지 않는다.
"""

from sqladmin import ModelView

from app.features.{name}.models.models import {_pascal(name)}


class {_pascal(name)}Admin(ModelView, model={_pascal(name)}):
    """{_pascal(name)} 관리자 뷰."""

    name = "{_pascal(name)}"
    column_list = [{_pascal(name)}.id]


admin_views: list[type[ModelView]] = [{_pascal(name)}Admin]
'''


def _service(name: str) -> str:
    return f'''"""{_pascal(name)} 유스케이스."""


class {_pascal(name)}Service:
    """{_pascal(name)} 비즈니스 규칙 — Repository 를 주입받아 사용한다."""
'''


def _tests(name: str) -> str:
    return f'''"""{_pascal(name)} 앱 테스트.

이 앱이 ``config.INSTALLED_APPS`` 에 등록된 뒤에만 route 가 존재한다.
"""

from app.core.apps import Apps
from config import INSTALLED_APPS


def test_app_is_registered():
    registry = Apps()
    registry.populate(INSTALLED_APPS, run_ready=False)

    assert registry.is_installed(
        "app.features.{name}"
    ), "config.INSTALLED_APPS 에 app.features.{name}.apps.{_pascal(name)}Config 를 추가하세요."
'''


def build_files(name: str, *, with_models: bool, with_admin: bool) -> dict[str, str]:
    """생성할 (상대경로 → 내용) 매핑을 만든다."""
    files: dict[str, str] = {
        "__init__.py": _package_init(name),
        "apps.py": _apps_py(name),
        "api/__init__.py": "",
        "api/routers/__init__.py": "",
        "api/routers/router.py": _router(name),
        "api/routers/v1/__init__.py": "",
        f"api/routers/v1/{name}.py": _v1_view(name),
        "services/__init__.py": "",
        f"services/{name}_service.py": _service(name),
        "dependencies/__init__.py": "",
        "repositories/__init__.py": "",
        "schemas/__init__.py": "",
        "tests/__init__.py": "",
        f"tests/test_{name}.py": _tests(name),
    }
    if with_models or with_admin:
        files["models/__init__.py"] = _models_init(name)
        files["models/models.py"] = _models(name)
    if with_admin:
        files["admin.py"] = _admin(name)
    return files


# =============================================================================
# 생성
# =============================================================================
def create_app_scaffold(
    name: str,
    *,
    with_models: bool = False,
    with_admin: bool = False,
    features_dir: Path = FEATURES_DIR,
) -> Path:
    """앱 골격을 만들고 최종 경로를 돌려준다.

    임시 디렉터리에서 전체를 만든 뒤 통째로 옮긴다 — 중간에 실패해도 ``app/features``
    아래에 반쯤 만들어진 앱이 남지 않는다(SEC-04).

    Raises:
        AppScaffoldError: 이름이 잘못됐거나 대상이 이미 존재한다.
    """
    target = resolve_target(name, features_dir)
    if target.exists():
        raise AppScaffoldError(
            f"'{target}' 이 이미 존재합니다. 기존 앱을 덮어쓰지 않습니다. "
            "다른 이름을 쓰거나 기존 디렉터리를 직접 정리하세요."
        )

    files = build_files(name, with_models=with_models, with_admin=with_admin)
    staging = Path(tempfile.mkdtemp(prefix=f"newapp_{name}_"))
    try:
        build_root = staging / name
        for relative, content in files.items():
            path = build_root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(build_root), str(target))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target


def config_entry(name: str) -> str:
    """``config.INSTALLED_APPS`` 에 붙여 넣을 한 줄."""
    return f'    "app.features.{name}.apps.{_pascal(name)}Config",'


def next_steps(name: str, *, with_admin: bool = False) -> str:
    """생성 후 사용자가 해야 할 일 — 등록이 첫 단계다."""
    admin_note = (
        "\n5. Admin 은 ADMIN=true 인 환경에서만 등록된다(운영에서는 비활성 권장)."
        if with_admin
        else ""
    )
    return f"""
생성 완료: app/features/{name}/

이 앱은 아직 **설치되지 않았다.** config.py 의 INSTALLED_APPS 에 아래 한 줄을 추가해야
Router·Models·Admin·ready() 가 활성화된다.

INSTALLED_APPS: list[str] = [
    ...
{config_entry(name)}
]

다음 단계
1. 위 한 줄을 config.py 에 추가한다.
2. 모델을 정의했다면 migration 을 만들고 적용한다:
     uv run alembic revision --autogenerate -m "add {name}"
     uv run alembic upgrade head
3. 라우트 확인: GET /api/v1/{name}/ping
4. 테스트: uv run python -m pytest app/features/{name}{admin_note}
""".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.new_app",
        description="신규 기능 앱 골격을 만든다 (설정 파일은 수정하지 않는다).",
    )
    parser.add_argument("name", help="앱 이름 (snake_case, 예: orders)")
    parser.add_argument("--with-models", action="store_true", help="models 골격을 만든다")
    parser.add_argument(
        "--with-admin", action="store_true", help="admin_views 골격을 만든다 (models 포함)"
    )
    args = parser.parse_args(argv)

    try:
        create_app_scaffold(args.name, with_models=args.with_models, with_admin=args.with_admin)
    except AppScaffoldError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    print(next_steps(args.name, with_admin=args.with_admin))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
