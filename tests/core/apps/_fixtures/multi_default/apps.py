from app.core.apps import AppConfig


class SecondaryConfig(AppConfig):
    name = "tests.core.apps._fixtures.multi_default"
    label = "multi_secondary"


class PrimaryConfig(AppConfig):
    name = "tests.core.apps._fixtures.multi_default"
    label = "multi_primary"
    default = True
