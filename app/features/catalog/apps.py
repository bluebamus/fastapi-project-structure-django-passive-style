"""Catalog 앱 설정."""

from app.core.apps import AppConfig


class CatalogConfig(AppConfig):
    """상품 카탈로그 기능 앱 (ORM 예제)."""

    name = "app.features.catalog"
