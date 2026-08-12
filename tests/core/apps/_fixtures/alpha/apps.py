from app.core.apps import AppConfig
from tests.core.apps._fixtures.eventlog import record


class AlphaConfig(AppConfig):
    name = "tests.core.apps._fixtures.alpha"

    def ready(self) -> None:
        record("ready", "alpha")
