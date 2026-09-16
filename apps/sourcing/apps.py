from django.apps import AppConfig


class SourcingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.sourcing"
    verbose_name = "Sourcing Directory"

    def ready(self):
        from . import checks  # noqa: F401
