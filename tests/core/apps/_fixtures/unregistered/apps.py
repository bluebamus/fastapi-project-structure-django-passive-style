from app.core.apps import AppConfig
from tests.core.apps._fixtures.eventlog import record


class UnregisteredConfig(AppConfig):
    name = "tests.core.apps._fixtures.unregistered"

    def ready(self) -> None:
        record("ready", "unregistered")
