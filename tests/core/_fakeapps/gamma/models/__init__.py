"""models 패키지 자체는 있으나 내부 import 가 깨진 경우."""

import totally_missing_dependency_xyz  # noqa: F401
