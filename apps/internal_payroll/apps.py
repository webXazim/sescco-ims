from django.apps import AppConfig


class InternalPayrollConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.internal_payroll"
    verbose_name = "Internal Payroll"

    def ready(self):
        from . import checks  # noqa: F401
