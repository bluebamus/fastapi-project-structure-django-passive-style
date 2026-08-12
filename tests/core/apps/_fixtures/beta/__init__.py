"""beta fixture 앱 — root package import 를 기록한다."""

from tests.core.apps._fixtures.eventlog import record

record("config", "beta")
