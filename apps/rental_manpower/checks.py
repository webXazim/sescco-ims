from __future__ import annotations

from django.core.checks import Error, Tags, register


@register(Tags.models, deploy=True)
def rental_manpower_merge_contract_checks(app_configs, **kwargs):
    """Protect Rental Manpower's merged identity, tenant and shared-project contracts."""

    from django.apps import apps as django_apps
    from django.conf import settings

    issues = []
    if settings.AUTH_USER_MODEL != "accounts.User":
        issues.append(
            Error(
                "Rental Manpower must use the existing IMS accounts.User identity model.",
                id="payroll.E301",
            )
        )

    config = django_apps.get_app_config("rental_manpower")
    models = list(config.get_models())
    if any(model.__name__ == "RentalProject" for model in models):
        issues.append(
            Error(
                "Rental Manpower reintroduced a duplicate RentalProject model.",
                hint="Use projects.Project for every rental project relationship.",
                id="payroll.E302",
            )
        )

    for model in models:
        if not any(field.name == "company" for field in model._meta.fields):
            issues.append(
                Error(
                    f"{model._meta.label} is missing direct company ownership.",
                    hint="Every Rental Manpower business record must remain inside the shared Company tenant boundary.",
                    id="payroll.E303",
                )
            )

    expected_project_models = {
        "WorkerAssignment",
        "RentalTimesheetPeriod",
        "RentalAdjustment",
        "SupplierSettlement",
    }
    for model_name in expected_project_models:
        model = django_apps.get_model("rental_manpower", model_name)
        field = model._meta.get_field("project")
        target = field.remote_field.model._meta.label_lower
        if target != "projects.project":
            issues.append(
                Error(
                    f"{model._meta.label}.project points to {target} instead of projects.Project.",
                    id="payroll.E304",
                )
            )
    return issues
