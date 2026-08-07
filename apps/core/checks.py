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

    return issues
