"""``Apps`` — 설치된 앱의 중앙 registry.

Django 의 app registry lifecycle 을 그대로 옮긴다. 앱은 ``INSTALLED_APPS`` 순서대로
**단계별로** 초기화된다 — 모든 앱의 config 가 끝난 뒤 models 로, 모든 앱의 models 가
끝난 뒤 ``ready()`` 로 넘어간다. 앱 하나를 끝까지 처리하고 다음으로 가는 방식이
아니다. 그래야 어떤 ``ready()`` 든 **모든** 앱의 model 을 볼 수 있다.

lifecycle 보호가 정확성의 핵심이다:

* **idempotent** — 두 번째 ``populate()`` 는 no-op. ``ready()`` 가 두 번 돌면 sink 나
  signal 이 중복 등록된다.
* **non-reentrant** — population 도중의 재호출은 ``RuntimeError``. 반쯤 채워진
  registry 를 읽는 코드가 조용히 잘못된 답을 얻는 것보다 낫다.
* **thread-safe** — ``RLock`` 으로 직렬화한다. 늦게 온 스레드는 완성된 registry 를 본다.
* **실패 시 원복** — 중간에 터지면 상태를 전부 되돌린다. partially-ready registry 가
  전역에 남아 다음 실행이 성공한 것처럼 보이면 안 된다(NFR-04).
"""

from __future__ import annotations

import threading
from collections import Counter
from collections.abc import Sequence

from app.core.apps.config import AppConfig
from app.core.apps.exceptions import (
    AppLookupError,
    AppRegistryNotReady,
    ImproperlyConfigured,
)


class Apps:
    """설치된 앱의 registry.

    전역 인스턴스는 ``app.core.apps.apps`` 이지만, 테스트와 app factory 는 독립
    인스턴스를 만들어 상태를 격리할 수 있다(NFR-05).
    """

    def __init__(self) -> None:
        self.app_configs: dict[str, AppConfig] = {}
        self.apps_ready = False
        self.models_ready = False
        self.ready = False
        self.loading = False
        self._populated = False
        self._entries: list[str] = []
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # population
    # ------------------------------------------------------------------
    def populate(self, installed_apps: Sequence[str], *, run_ready: bool = True) -> None:
        """``installed_apps`` 를 순서대로 3단계 초기화한다.

        Args:
            installed_apps: ``config.INSTALLED_APPS`` — package 경로 또는 config
                class 경로의 목록.
            run_ready: ``False`` 면 config·models 단계까지만 수행하고 ``ready()`` hook 을
                건너뛴다. **Alembic adapter 전용** 이다 — migration 이 앱의 runtime
                부수효과를 실행하지 않게 한다(§6.7). 애플리케이션 조립부는 쓰지 않는다.

        Raises:
            RuntimeError: population 도중 재진입했다.
            ImproperlyConfigured: 등록 항목이 잘못됐다.
        """
        with self._lock:
            if self._populated and (self.ready or not run_ready):
                return
            if self.loading:
                raise RuntimeError(
                    "app registry populate() 가 이미 진행 중입니다 (재진입 금지). "
                    "AppConfig.ready() 안에서 populate() 를 부르지 마세요."
                )

            self.loading = True
            try:
                if not self._populated:
                    self._load_configs(list(installed_apps))
                    self.apps_ready = True
                    self._import_models()
                    self.models_ready = True
                    self._populated = True
                if run_ready:
                    self._run_ready()
                    self.ready = True
            except BaseException:
                self._reset()
                raise
            finally:
                self.loading = False

    def _load_configs(self, entries: list[str]) -> None:
        """1단계 — 각 항목을 ``AppConfig`` 로 정규화하고 root package 를 import 한다."""
        duplicates = sorted(name for name, count in Counter(entries).items() if count > 1)
        if duplicates:
            raise ImproperlyConfigured(
                f"config.INSTALLED_APPS 에 중복된 항목이 있습니다: {duplicates}. "
                "각 앱은 한 번만 등록합니다."
            )

        by_name: dict[str, str] = {}
        for entry in entries:
            config = AppConfig.create(entry)
            if config.name in by_name:
                raise ImproperlyConfigured(
                    f"앱 name '{config.name}' 이 두 번 등록됐습니다 "
                    f"('{by_name[config.name]}' 와 '{entry}'). "
                    "config.INSTALLED_APPS 에서 하나를 지우세요."
                )
            if config.label in self.app_configs:
                other = self.app_configs[config.label]
                raise ImproperlyConfigured(
                    f"앱 label '{config.label}' 이 중복입니다 "
                    f"('{other.name}' 와 '{config.name}'). "
                    "한쪽 AppConfig 에 다른 label 을 지정하세요."
                )
            by_name[config.name] = entry
            self.app_configs[config.label] = config
        self._entries = entries

    def _import_models(self) -> None:
        """2단계 — 설치 앱의 models module 을 목록 순서대로 import 한다."""
        for config in self.app_configs.values():
            config.import_models()

    def _run_ready(self) -> None:
        """3단계 — 설치 앱의 ``ready()`` hook 을 목록 순서대로 호출한다."""
        for config in self.app_configs.values():
            config.ready()

    def _reset(self) -> None:
        self.app_configs.clear()
        self._entries = []
        self.apps_ready = False
        self.models_ready = False
        self.ready = False
        self._populated = False

    # ------------------------------------------------------------------
    # 조회 API
    # ------------------------------------------------------------------
    def check_apps_ready(self) -> None:
        """config 단계가 끝났는지 확인한다."""
        if not self.apps_ready:
            raise AppRegistryNotReady(
                "app registry 가 아직 준비되지 않았습니다. populate() 를 먼저 호출하세요."
            )

    def check_models_ready(self) -> None:
        """models 단계가 끝났는지 확인한다."""
        if not self.models_ready:
            raise AppRegistryNotReady(
                "app registry 의 model 이 아직 로드되지 않았습니다. populate() 를 먼저 호출하세요."
            )

    def get_app_configs(self) -> list[AppConfig]:
        """설치 앱의 ``AppConfig`` 를 ``INSTALLED_APPS`` 순서로 돌려준다."""
        self.check_apps_ready()
        return list(self.app_configs.values())

    def get_app_config(self, label: str) -> AppConfig:
        """label 로 ``AppConfig`` 를 찾는다. 없으면 :class:`AppLookupError`."""
        self.check_apps_ready()
        try:
            return self.app_configs[label]
        except KeyError as exc:
            installed = ", ".join(self.app_configs) or "(없음)"
            raise AppLookupError(
                f"app label '{label}' 이 설치되어 있지 않습니다. 설치된 앱: {installed}"
            ) from exc

    def is_installed(self, app_name: str) -> bool:
        """전체 package 경로로 설치 여부를 확인한다."""
        self.check_apps_ready()
        return any(config.name == app_name for config in self.app_configs.values())

    def get_models(self) -> list[type]:
        """설치 앱의 모든 매핑 model 을 등록 순서로 돌려준다."""
        self.check_models_ready()
        return [model for config in self.app_configs.values() for model in config.get_models()]

    def get_model(self, app_label: str, model_name: str, *, require_ready: bool = True) -> type:
        """``app_label`` 의 model 을 대소문자 구분 없이 찾는다.

        Args:
            require_ready: ``False`` 면 models 단계 완료 검사를 건너뛴다 —
                population 중 진단 코드에서만 쓴다.
        """
        if require_ready:
            self.check_models_ready()
        return self.get_app_config(app_label).get_model(model_name)
