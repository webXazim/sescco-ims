from django.apps import AppConfig


class RentalManpowerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.rental_manpower"
    verbose_name = "Rental Manpower"

    def ready(self):
        from . import checks  # noqa: F401
