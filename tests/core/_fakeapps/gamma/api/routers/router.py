"""선택 모듈은 존재하지만 그 내부 import 가 깨진 앱 — 조용히 넘어가면 안 된다."""

import totally_missing_dependency_xyz  # noqa: F401

gamma_router = None
