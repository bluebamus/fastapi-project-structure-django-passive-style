"""SNS 앱 설정."""

from app.core.apps import AppConfig


class SnsConfig(AppConfig):
    """SNS 기능 앱."""

    name = "app.features.sns"
    verbose_name = "SNS"
