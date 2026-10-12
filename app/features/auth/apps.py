"""Auth 앱 설정."""

from app.core.apps import AppConfig


class AuthConfig(AppConfig):
    """Auth 기능 앱.

    자체 모델이 없다 — user 기능의 ``User`` 에 대해 인증한다. registry 는 models
    모듈이 없는 앱을 정상으로 처리하므로 추가 선언이 필요 없다.

    ``ready()`` 에서 ``/admin`` 로그인의 자격 확인 팩토리를 core 훅에 등록한다(admin-login
    ADR-002). 등록은 process-local wiring 이다(SEC-05) — 팩토리는 관리 화면(``ADMIN_DISABLED=false``)을
    조립할 때만 불린다.
    """

    name = "app.features.auth"

    def ready(self) -> None:
        from app.core.security.admin_credentials import register_admin_credentials
        from app.features.auth.admin_credentials import default_admin_credentials

        register_admin_credentials(default_admin_credentials)
