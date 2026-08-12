from app.core.apps import AppConfig
from tests.core.apps._fixtures.eventlog import record


class BetaConfig(AppConfig):
    name = "tests.core.apps._fixtures.beta"

    def ready(self) -> None:
        record("ready", "beta")
