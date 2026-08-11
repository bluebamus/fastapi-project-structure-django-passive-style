"""앱 패키지 자체는 존재하지만 import-time 부수효과가 깨진 앱."""

import totally_missing_dependency_xyz  # noqa: F401
