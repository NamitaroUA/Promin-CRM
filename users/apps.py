from django.apps import AppConfig


class UsersConfig(AppConfig):
    name = 'users'

    def ready(self):
        # Register signal handlers (users/signals.py)
        from . import signals  # noqa: F401
