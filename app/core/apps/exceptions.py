"""App registry 예외 계층.

세 가지를 서로 다른 타입으로 구분한다 — 섞이면 호출자가 "설정을 고쳐야 하는 문제"
와 "아직 안 불렀을 뿐인 문제" 를 구별하지 못한다.

* :class:`ImproperlyConfigured` — ``config.INSTALLED_APPS`` 를 사람이 고쳐야 한다.
* :class:`AppRegistryNotReady` — 준비되지 않은 registry 를 조회했다(호출 순서 문제).
* :class:`AppLookupError` — 등록은 됐지만 그 label/model 이 없다.

앱 package·module **내부** 의 import 실패는 여기서 감싸지 않는다. 원래
``ModuleNotFoundError`` 를 그대로 전파해 누락된 dependency 이름과 traceback 을
보존한다(NFR-03·SEC-07).
"""


class AppRegistryError(Exception):
    """app registry 관련 오류의 공통 base."""


class ImproperlyConfigured(AppRegistryError):
    """``INSTALLED_APPS`` 항목이나 ``AppConfig`` 선언이 잘못됐다."""


class AppRegistryNotReady(AppRegistryError):
    """population 이 끝나기 전에 registry 를 조회했다."""


class AppLookupError(AppRegistryError, LookupError):
    """요청한 app label 또는 model 이 registry 에 없다.

    ``LookupError`` 를 겸하는 이유는 Django 의 ``apps.get_model()`` 이 ``LookupError``
    를 던지기 때문이다 — 기존 ``except LookupError`` 코드가 그대로 동작한다.
    """
