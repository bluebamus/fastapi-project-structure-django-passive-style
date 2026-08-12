"""``AppConfig`` — 설치된 앱 하나의 정규화된 표현.

Django ``django.apps.AppConfig`` 의 공개 의미(``name``·``label``·``verbose_name``·
``path``·``ready()``)를 보존하되, ORM 과 웹 프레임워크는 이 프로젝트의 것을 쓴다.

**framework-neutral 이다** — 이 모듈은 FastAPI 도 SQLAdmin 도 SQLAlchemy 도 import
하지 않는다(NFR-06). Router 와 admin_views 는 "그 이름의 속성을 가져온다" 수준으로만
다루고, 그것으로 무엇을 하는지는 ``app/core/apps/wiring.py`` 의 adapter 가 정한다.

등록 항목 해석(``create()``)은 Django 규칙 그대로다.

1. entry 를 module 로 import 해본다. 되면 **package 등록** 이다.
2. package 등록이면 ``<package>.apps`` 에서 기본 config 를 고른다
   (0개 → 기본 ``AppConfig``, 1개 → 그것, 복수 → ``default=True`` 하나).
3. import 가 "그 module 자체가 없다" 로 실패하면 **config class 경로** 로 본다.
4. 그 외의 ``ModuleNotFoundError`` 는 앱 내부의 구현 오류이므로 그대로 전파한다.
"""

from __future__ import annotations

import importlib
import keyword
from pathlib import Path
from types import ModuleType
from typing import Any

from app.core.apps.exceptions import AppLookupError, ImproperlyConfigured


def module_is_absent(exc: ModuleNotFoundError, target: str) -> bool:
    """``exc`` 가 "``target`` 자체가 없다" 를 뜻하는지 판정한다.

    ``target`` 을 import 하다 터진 ``ModuleNotFoundError`` 는 두 가지다 —
    ``target`` (또는 그 상위 package)이 없는 경우와, ``target`` 은 있는데 그 안에서
    **다른** module 을 못 찾은 경우. 후자는 선택 기능 부재가 아니라 구현 오류다.

    판정은 ``exc.name`` 으로 한다. 문자열 매칭이 아니라 인터프리터가 알려준
    "못 찾은 module 이름" 을 쓰므로 오탐이 없다.
    """
    name = exc.name
    return name is not None and (target == name or target.startswith(f"{name}."))


def import_optional(dotted: str) -> ModuleType | None:
    """선택 module 을 import 한다 — 없으면 ``None``, 내부 오류면 전파.

    이 한 줄의 구분이 passive 등록의 핵심 안전장치다(NFR-03·SEC-07).
    """
    try:
        return importlib.import_module(dotted)
    except ModuleNotFoundError as exc:
        if module_is_absent(exc, dotted):
            return None
        raise


def _is_mapped_class(obj: object) -> bool:
    """SQLAlchemy declarative 매핑이 끝난 class 인지 본다.

    ``sqlalchemy`` 를 import 하지 않으려고 mapper 속성 존재로 판정한다 — registry
    core 를 ORM 에 묶지 않기 위해서다(NFR-06).
    """
    return isinstance(obj, type) and hasattr(obj, "__mapper__")


class AppConfig:
    """설치된 앱 하나의 설정과 introspection 지점.

    Attributes:
        name: 앱의 전체 Python package 경로. subclass 가 반드시 선언한다.
        label: 프로젝트 안에서 유일한 짧은 이름. 기본값은 ``name`` 의 마지막 조각.
        verbose_name: 사람이 읽는 이름. 기본값은 label 의 title 표현.
        path: 앱 package 의 파일 시스템 경로.
        default: ``<package>.apps`` 에 config 가 여럿일 때의 선택 표시.
        module: import 된 앱 root package.
    """

    name: str
    label: str
    verbose_name: str
    default: bool | None = None

    #: 앱 package 기준 상대 module 경로 — 결선 컨벤션.
    router_module: str = "api.routers.router"
    #: ``None`` 이면 ``<label>_router`` 를 쓴다.
    router_attribute: str | None = None
    models_module: str = "models"
    admin_module: str = "admin"
    #: 이 앱 router 를 붙일 prefix. 앱별로 바꿀 수 있다.
    router_prefix: str = "/api"

    def __init__(self, app_name: str, app_module: ModuleType) -> None:
        cls = type(self)
        self.name = app_name
        self.module = app_module

        label = getattr(cls, "label", None)
        if label is None:
            label = app_name.rpartition(".")[2]
        if not label.isidentifier() or keyword.iskeyword(label):
            raise ImproperlyConfigured(
                f"앱 '{app_name}' 의 label '{label}' 이 유효한 Python identifier 가 아닙니다. "
                f"{cls.__module__}.{cls.__qualname__} 의 label 을 고치세요."
            )
        self.label = label

        verbose_name = getattr(cls, "verbose_name", None)
        self.verbose_name = (
            verbose_name if verbose_name is not None else label.replace("_", " ").title()
        )

        self.path = self._resolve_path(app_name, app_module)
        if self.router_attribute is None:
            self.router_attribute = f"{label}_router"

        self._models: dict[str, type] = {}
        self._models_imported = False

    def __repr__(self) -> str:
        return f"<{type(self).__name__}: {self.label}>"

    # ------------------------------------------------------------------
    # 등록 항목 해석
    # ------------------------------------------------------------------
    @classmethod
    def create(cls, entry: str) -> AppConfig:
        """``INSTALLED_APPS`` 항목 하나를 ``AppConfig`` 인스턴스로 정규화한다."""
        app_module: ModuleType | None
        try:
            app_module = importlib.import_module(entry)
        except ModuleNotFoundError as exc:
            if not module_is_absent(exc, entry):
                # entry 자체는 있는데 그 안의 import 가 깨졌다 — 앱 구현 오류다.
                raise
            app_module = None

        if app_module is not None:
            config_class = cls._select_config_class(entry) or AppConfig
            return config_class(entry, app_module)

        config_class = cls._load_config_class(entry)
        app_name = getattr(config_class, "name", None)
        if not app_name:
            raise ImproperlyConfigured(
                f"config.INSTALLED_APPS 의 '{entry}' 가 가리키는 "
                f"{config_class.__qualname__} 에 name 속성이 없습니다. "
                "AppConfig subclass 는 name 에 앱 package 경로를 선언해야 합니다."
            )
        return config_class(app_name, importlib.import_module(app_name))

    @classmethod
    def _select_config_class(cls, package: str) -> type[AppConfig] | None:
        """``<package>.apps`` 에서 기본 config 를 고른다 (CR-01).

        Returns:
            선택된 subclass. ``apps`` module 이 없거나 후보가 0개면 ``None``.
        """
        dotted = f"{package}.apps"
        module = import_optional(dotted)
        if module is None:
            return None

        # 다른 module 에서 import 해 온 config 는 후보가 아니다 — 이 앱이 선언한 것만
        # 본다. (열거 순서는 dict 삽입 순서라 실행마다 동일하다 — NFR-01)
        candidates = [
            obj
            for obj in vars(module).values()
            if isinstance(obj, type)
            and issubclass(obj, AppConfig)
            and obj is not AppConfig
            and obj.__module__ == dotted
        ]
        selectable = [obj for obj in candidates if obj.default is not False]
        if len(selectable) == 1:
            return selectable[0]
        if not selectable:
            return None

        defaults = [obj for obj in selectable if obj.default is True]
        if len(defaults) == 1:
            return defaults[0]
        names = ", ".join(sorted(obj.__qualname__ for obj in selectable))
        raise ImproperlyConfigured(
            f"'{dotted}' 에 AppConfig 가 여러 개 있어 기본값을 고를 수 없습니다: {names}. "
            "하나에만 default = True 를 지정하거나, config.INSTALLED_APPS 에 "
            "사용할 config class 경로를 직접 적으세요."
        )

    @classmethod
    def _load_config_class(cls, entry: str) -> type[AppConfig]:
        """entry 를 explicit config class 경로로 해석한다 (CR-02)."""
        module_path, _, class_name = entry.rpartition(".")
        unresolved = (
            f"config.INSTALLED_APPS 의 항목 '{entry}' 를 해석할 수 없습니다. "
            f"package '{entry}' 도, module '{module_path}' 의 '{class_name}' 속성도 "
            "찾지 못했습니다."
        )
        if not module_path:
            raise ImproperlyConfigured(unresolved)

        try:
            module = importlib.import_module(module_path)
        except ModuleNotFoundError as exc:
            if not module_is_absent(exc, module_path):
                raise
            raise ImproperlyConfigured(unresolved) from exc

        try:
            candidate = getattr(module, class_name)
        except AttributeError as exc:
            raise ImproperlyConfigured(unresolved) from exc

        if not (isinstance(candidate, type) and issubclass(candidate, AppConfig)):
            raise ImproperlyConfigured(
                f"config.INSTALLED_APPS 의 '{entry}' 는 AppConfig subclass 가 아닙니다 "
                f"(실제: {type(candidate).__name__}). "
                "app.core.apps.AppConfig 를 상속한 class 경로를 적으세요."
            )
        return candidate

    @staticmethod
    def _resolve_path(app_name: str, app_module: ModuleType) -> Path:
        paths = [str(p) for p in getattr(app_module, "__path__", [])]
        if len(paths) != 1:
            raise ImproperlyConfigured(
                f"앱 '{app_name}' 의 파일 시스템 경로를 확정할 수 없습니다 "
                f"(후보 {len(paths)}개). 앱은 단일 디렉터리 package 여야 합니다."
            )
        return Path(paths[0]).resolve()

    # ------------------------------------------------------------------
    # population 단계 hook
    # ------------------------------------------------------------------
    def import_models(self) -> None:
        """앱의 models module 을 import 하고 매핑된 class 를 수집한다.

        models 가 없는 앱은 정상이다(기준 저장소의 ``auth`` 가 그렇다).
        """
        module = import_optional(f"{self.name}.{self.models_module}")
        self._models = {} if module is None else self._collect_models(module)
        self._models_imported = True

    def ready(self) -> None:
        """models 준비 후 실행할 앱별 초기화 hook.

        기본 구현은 아무것도 하지 않는다. 재정의할 때는 **process-local wiring 만**
        허용한다 — DB query, network call, subprocess 실행, secret 출력 금지(SEC-05).
        migration 과 CLI 도 이 hook 을 실행할 수 있기 때문이다.
        """

    def _collect_models(self, module: ModuleType) -> dict[str, type]:
        prefix = f"{self.name}."
        found: dict[str, type] = {}
        for obj in vars(module).values():
            if _is_mapped_class(obj) and str(obj.__module__).startswith(prefix):
                found[obj.__name__.lower()] = obj
        return found

    # ------------------------------------------------------------------
    # 조회 API
    # ------------------------------------------------------------------
    def get_models(self) -> list[type]:
        """이 앱에 속한 매핑 model class 목록(선언 순서)."""
        return list(self._models.values())

    def get_model(self, model_name: str) -> type:
        """model 을 대소문자 구분 없이 찾는다. 없으면 :class:`AppLookupError`."""
        try:
            return self._models[model_name.lower()]
        except KeyError as exc:
            available = ", ".join(sorted(self._models)) or "(없음)"
            raise AppLookupError(
                f"앱 '{self.label}' 에 model '{model_name}' 이 없습니다. 등록된 model: {available}"
            ) from exc

    # ------------------------------------------------------------------
    # 선택 구성요소 (adapter 가 사용한다)
    # ------------------------------------------------------------------
    def import_router(self) -> Any | None:
        """앱의 router 객체를 돌려준다. router module 이 없으면 ``None``."""
        return self._import_component(self.router_module, self.router_attribute or "")

    def import_admin_views(self) -> Any | None:
        """앱의 ``admin_views`` 를 돌려준다. admin module 이 없으면 ``None``."""
        return self._import_component(self.admin_module, "admin_views")

    def _import_component(self, relative_module: str, attribute: str) -> Any | None:
        dotted = f"{self.name}.{relative_module}"
        module = import_optional(dotted)
        if module is None:
            return None
        try:
            return getattr(module, attribute)
        except AttributeError as exc:
            raise ImproperlyConfigured(
                f"'{dotted}' 에 '{attribute}' 가 없습니다. "
                f"앱 '{self.label}' 의 결선 컨벤션을 확인하세요 "
                f"(module 이 존재하면 공개 이름도 있어야 합니다)."
            ) from exc
