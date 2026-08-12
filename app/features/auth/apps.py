"""Auth 앱 설정."""

from app.core.apps import AppConfig


class AuthConfig(AppConfig):
    """Auth 기능 앱.

    자체 모델이 없다 — user 기능의 ``User`` 에 대해 인증한다. registry 는 models
    모듈이 없는 앱을 정상으로 처리하므로 추가 선언이 필요 없다.
    """

    name = "app.features.auth"
