"""Home 앱 설정."""

from app.core.apps import AppConfig


class HomeConfig(AppConfig):
    """Home 기능 앱.

    ``ready()`` 에서 access-log sink 를 미들웨어에 연결한다. 예전에는 패키지
    ``__init__.py`` 의 import-time 부수효과였는데, 그러면 registry 1단계(root package
    import)에서 이미 sink 가 붙어 3단계 lifecycle 이 무의미해진다. hook 으로 옮기면
    "models 가 준비된 뒤에 결선한다" 는 순서가 코드로 보장된다.

    sink 등록은 process-local wiring 이라 SEC-05(ready 에서 DB·network·subprocess 금지)를
    지킨다 — ``set_access_log_sink()`` 는 모듈 전역 변수 하나를 바꿀 뿐이다.
    """

    name = "app.features.home"

    def ready(self) -> None:
        # 지연 import — 1단계(root package import)에서 서비스·모델이 딸려오지 않게 한다.
        from app.features.home.access_log_sink import register_sink

        register_sink()
