from app.core.apps import AppConfig


class BadLabelConfig(AppConfig):
    name = "tests.core.apps._fixtures.badlabel"
    label = "not-an-identifier"
