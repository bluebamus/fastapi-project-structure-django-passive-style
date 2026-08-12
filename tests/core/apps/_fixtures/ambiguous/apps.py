from app.core.apps import AppConfig


class OneConfig(AppConfig):
    name = "tests.core.apps._fixtures.ambiguous"
    label = "ambiguous_one"


class TwoConfig(AppConfig):
    name = "tests.core.apps._fixtures.ambiguous"
    label = "ambiguous_two"
