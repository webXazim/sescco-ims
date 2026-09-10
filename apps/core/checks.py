from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def inventory_deployment_checks(app_configs, **kwargs):
    issues = []

    if len(settings.SECRET_KEY) < 50:
        issues.append(
            Error(
                "DJANGO_SECRET_KEY must contain at least 50 characters.",
                id="inventory.E001",
            )
        )

    if "*" in settings.ALLOWED_HOSTS:
        issues.append(
            Error(
                "Wildcard ALLOWED_HOSTS is not permitted for this private deployment.",
                id="inventory.E002",
            )
        )

    insecure_origins = [
        origin
        for origin in settings.CSRF_TRUSTED_ORIGINS
        if urlparse(origin).scheme != "https"
    ]
    if insecure_origins:
        issues.append(
            Error(
                "All CSRF trusted origins must use HTTPS in production.",
                hint=", ".join(insecure_origins),
                id="inventory.E003",
            )
        )

    engine = settings.DATABASES["default"]["ENGINE"]
    if not engine.endswith("postgresql"):
        issues.append(
            Error(
                "Production inventory must use PostgreSQL.",
                id="inventory.E004",
            )
        )

    if settings.MEDIA_ROOT == settings.STATIC_ROOT:
        issues.append(
            Error(
                "MEDIA_ROOT and STATIC_ROOT must be separate.",
                id="inventory.E005",
            )
        )

    if settings.APP_VERSION in {"", "dev"}:
        issues.append(
            Warning(
                "APP_VERSION should identify the deployed release.",
                id="inventory.W001",
            )
        )

    payroll_assets = (
        settings.BASE_DIR / "static" / "payroll" / "js" / "app.js",
        settings.BASE_DIR / "static" / "payroll" / "css" / "v2" / "index.css",
        settings.BASE_DIR / "static" / "payroll" / "css" / "v2" / "prs-final.css",
        settings.BASE_DIR / "templates" / "payroll" / "app.html",
    )
    missing_payroll_assets = [str(path.relative_to(settings.BASE_DIR)) for path in payroll_assets if not path.is_file()]
    if missing_payroll_assets:
        issues.append(
            Error(
                "The merged Payroll frontend bundle is incomplete.",
                hint=f"Missing: {', '.join(missing_payroll_assets)}",
                id="platform.E201",
            )
        )

    return issues


@register(Tags.models, deploy=True)
def shared_project_authority_checks(app_configs, **kwargs):
    """Protect the merged platform from re-introducing Payroll's old duplicate project master."""

    from django.apps import apps as django_apps

    issues = []
    Project = django_apps.get_model("projects", "Project")
    required_fields = {"company", "reference", "code", "start_date", "end_date", "manager_name", "status"}
    actual_fields = {field.name for field in Project._meta.get_fields()}
    missing = sorted(required_fields - actual_fields)
    if missing:
        issues.append(
            Error(
                "The canonical shared Project contract is incomplete.",
                hint=f"Missing fields: {', '.join(missing)}",
                id="platform.E101",
            )
        )

    duplicate_model = django_apps.all_models.get("rental_manpower", {}).get("rentalproject")
    if duplicate_model is not None:
        issues.append(
            Error(
                "Rental Manpower must use projects.Project; a second RentalProject model is not allowed.",
                hint="Adapt Payroll foreign keys and services to apps.projects.Project instead of importing its standalone RentalProject.",
                id="platform.E102",
            )
        )
    return issues
