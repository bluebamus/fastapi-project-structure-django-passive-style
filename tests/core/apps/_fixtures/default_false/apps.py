from app.core.apps import AppConfig


class OptOutConfig(AppConfig):
    name = "tests.core.apps._fixtures.default_false"
    label = "opted_out"
    default = False
