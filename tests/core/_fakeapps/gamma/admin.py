"""admin 모듈 자체는 있으나 내부 import 가 깨진 경우."""

import totally_missing_dependency_xyz  # noqa: F401

admin_views: list[type] = []
