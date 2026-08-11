"""앱 등록 레지스트리 (수동 등록 목록 + 컨벤션 결선, gen-2).

앱 목록의 출처는 `config.INSTALLED_APPS` 하나뿐이다(자동 스캔 없음 — 그것이
자매 저장소 active-style 의 방식이다). 목록에 이름이 오른 앱에 한해, 그 안의
라우터·모델·Admin 을 네이밍 컨벤션으로 찾아 결선한다.

컨벤션 (app/features/<name>/):
    api/routers/router.py   →  <name>_router: APIRouter   (있으면 prefix /api 에 마운트)
    models/__init__.py      →  import 시 Base.metadata 에 테이블 등록 (선택)
    admin.py                →  admin_views: list[type]      (선택, SQLAdmin ModelView)
    __init__.py             →  import-time 부수효과(예: 미들웨어 sink 등록) (선택)

브랜치 차이는 오직 "앱 목록의 출처"뿐이다:
    - feature(자동): discover() 가 app/features/* 를 스캔해 목록을 만든다.
    - main(수동):    discover() 가 config.INSTALLED_APPS 목록을 읽는다.  ← 이 브랜치
결선(install_routers/import_models/install_admin)은 두 브랜치가 동일하게 공유한다.

선택 모듈(router/models/admin)이 **없는 것**과 그 모듈 내부의 import 가
**깨진 것**은 구분한다 — 둘 다 ModuleNotFoundError 로 오지만, 후자를 삼키면
앱의 일부가 조용히 비활성화된 채 서버가 정상 기동한다.
"""

from __future__ import annotations

import importlib
from collections import Counter
from dataclasses import dataclass

from fastapi import APIRouter

from app.utils.logs import get_logger

logger = get_logger("registry")

FEATURES_PACKAGE = "app.features"


def _is_absent(exc: ModuleNotFoundError, target: str) -> bool:
    """*target* 모듈(또는 그 상위 패키지)이 없어서 난 오류인가.

    ``exc.name`` 은 실제로 찾지 못한 모듈 이름이다. 그것이 우리가 찾던 경로
    자체이거나 그 상위 패키지일 때만 "선택 모듈 부재" 이고, 그 외에는 모듈
    안에서 다른 것을 import 하다 실패한 것 — 즉 구현 오류다.
    """
    name = exc.name
    return name is not None and (target == name or target.startswith(f"{name}."))


@dataclass(frozen=True)
class AppModule:
    """발견된 도메인 앱. 이름·패키지 경로만으로 구성요소를 컨벤션으로 찾는다.

    Attributes:
        name: 앱 이름 (예: "home"). 라우터 변수명 컨벤션의 기준.
        package: 앱 패키지 dotted 경로 (예: "app.features.home").
        prefix: 라우터 마운트 prefix.
    """

    name: str
    package: str
    prefix: str = "/api"

    @property
    def router_attr(self) -> str:
        """컨벤션 라우터 변수명 (예: home → home_router)."""
        return f"{self.name}_router"

    def load_router(self) -> APIRouter | None:
        """`<package>.api.routers.router` 의 `<name>_router` 를 반환. 없으면 None.

        Raises:
            ModuleNotFoundError: 라우터 모듈은 있으나 그 안의 import 가 실패한 경우.
        """
        target = f"{self.package}.api.routers.router"
        try:
            module = importlib.import_module(target)
        except ModuleNotFoundError as exc:
            if _is_absent(exc, target):
                return None
            raise
        return getattr(module, self.router_attr, None)

    def load_admin_views(self) -> list[type]:
        """`<package>.admin` 의 모듈 레벨 `admin_views` 리스트를 반환. 없으면 [].

        Raises:
            ModuleNotFoundError: admin 모듈은 있으나 그 안의 import 가 실패한 경우.
        """
        target = f"{self.package}.admin"
        try:
            module = importlib.import_module(target)
        except ModuleNotFoundError as exc:
            if _is_absent(exc, target):
                return []
            raise
        return list(getattr(module, "admin_views", []))

    def import_models(self) -> None:
        """`<package>.models` 를 import 하여 테이블을 Base.metadata 에 등록한다(있으면).

        Raises:
            ModuleNotFoundError: models 패키지는 있으나 그 안의 import 가 실패한 경우.
                조용히 넘기면 테이블이 metadata 에서 빠진 채 migration 이 만들어진다.
        """
        target = f"{self.package}.models"
        try:
            importlib.import_module(target)
        except ModuleNotFoundError as exc:
            if _is_absent(exc, target):
                return
            raise


class AppRegistry:
    """도메인 앱 자동발견 레지스트리 (컨벤션 기반)."""

    def __init__(self) -> None:
        self._apps: list[AppModule] = []

    @property
    def enabled_apps(self) -> list[AppModule]:
        """마지막 discover() 결과."""
        return self._apps

    def discover(self, package: str = FEATURES_PACKAGE) -> list[AppModule]:
        """`config.INSTALLED_APPS` 목록을 읽어 도메인 앱을 등록한다(수동 등록).

        앱 = INSTALLED_APPS 에 나열된 이름. `package`(기본 app.features) 하위에서
        `<package>.<name>` 패키지로 매핑한다. 목록 순서를 그대로 보존하여(정렬 없음)
        명시적 로드 순서 제어를 제공한다. 각 앱 패키지를 import 하여 import-time
        부수효과(__init__.py, 예: home 의 sink 등록)를 실행한다.

        feature 브랜치는 이 메서드만 app/features/* 자동 스캔으로 교체하고,
        결선 로직(install_routers/import_models/install_admin)은 동일하게 공유한다.

        Raises:
            ValueError: 목록에 같은 앱이 두 번 이상 있는 경우.
            ImportError: 목록의 이름에 해당하는 앱 패키지가 없는 경우.
        """
        from config import INSTALLED_APPS

        duplicates = sorted(name for name, n in Counter(INSTALLED_APPS).items() if n > 1)
        if duplicates:
            raise ValueError(
                f"config.INSTALLED_APPS 에 중복된 앱이 있습니다: {duplicates}. "
                "같은 앱을 두 번 등록하면 라우터가 중복 마운트됩니다."
            )

        apps = [AppModule(name=name, package=f"{package}.{name}") for name in INSTALLED_APPS]

        # import-time 부수효과(예: home 의 access-log sink 등록)를 위해 패키지 import
        for app in apps:
            try:
                importlib.import_module(app.package)
            except ModuleNotFoundError as exc:
                if not _is_absent(exc, app.package):
                    raise  # 앱은 있는데 그 안이 깨진 것 — 원인을 바꾸지 않는다
                raise ImportError(
                    f"config.INSTALLED_APPS 의 '{app.name}' 에 해당하는 앱 패키지를 찾을 수 "
                    f"없습니다 (찾은 경로: {app.package}). 앱 이름의 오타이거나 아직 "
                    "만들지 않은 앱입니다."
                ) from exc

        self._apps = apps
        logger.debug("installed %d apps: %s", len(apps), [a.name for a in apps])
        return self._apps

    def install_routers(self, app) -> int:
        """발견된 각 앱의 `<name>_router` 를 FastAPI 앱에 마운트한다."""
        count = 0
        for module in self._apps:
            router = module.load_router()
            if router is None:
                logger.warning(
                    "앱 '%s' 에 %s 라우터가 없어 건너뜀", module.name, module.router_attr
                )
                continue
            app.include_router(router, prefix=module.prefix)
            count += 1
        return count

    def import_models(self) -> None:
        """발견된 각 앱의 models 패키지를 import 한다(Base.metadata 등록)."""
        for module in self._apps:
            module.import_models()

    def install_admin(self, admin) -> int:
        """발견된 각 앱의 admin.py `admin_views` 를 SQLAdmin 에 등록한다."""
        count = 0
        for module in self._apps:
            for view in module.load_admin_views():
                admin.add_view(view)
                count += 1
        return count
