"""Django 호환 application registry.

``config.INSTALLED_APPS`` 가 설치 앱의 유일한 진실 공급원이고, 이 package 가 그
목록을 ``AppConfig`` 로 정규화해 3단계로 초기화한다. 디렉터리를 만드는 것만으로는
앱이 설치되지 않는다 — 목록에 넣어야 한다(FR-01).

``apps`` 는 프로세스 전역 기본 registry다. 테스트와 격리가 필요한 app factory 는
``Apps()`` 를 직접 만들어 주입한다(NFR-05).

FastAPI Router·SQLAdmin 결선은 이 package 가 아니라
:mod:`app.core.apps.wiring` 의 adapter 가 담당한다 — Django lifecycle 자체와 이
프로젝트 전용 확장을 섞지 않기 위해서다(CR-08·NFR-06).
"""

from app.core.apps.config import AppConfig
from app.core.apps.exceptions import (
    AppLookupError,
    AppRegistryError,
    AppRegistryNotReady,
    ImproperlyConfigured,
)
from app.core.apps.registry import Apps

#: 프로세스 전역 기본 registry.
apps = Apps()

__all__ = [
    "AppConfig",
    "AppLookupError",
    "AppRegistryError",
    "AppRegistryNotReady",
    "Apps",
    "ImproperlyConfigured",
    "apps",
]
