"""Reports 앱 설정."""

from app.core.apps import AppConfig


class ReportsConfig(AppConfig):
    """매출 리포트 기능 앱 (Raw SQL 예제)."""

    name = "app.features.reports"
