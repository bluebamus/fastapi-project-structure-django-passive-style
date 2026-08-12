"""INSTALLED_APPS 에 넣지 않는 fixture 앱 — 로드되면 안 된다."""

from tests.core.apps._fixtures.eventlog import record

record("config", "unregistered")
