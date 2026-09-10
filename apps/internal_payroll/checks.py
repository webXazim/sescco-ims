from __future__ import annotations

from django.core.checks import Error, Tags, register


@register(Tags.models, deploy=True)
def internal_payroll_merge_contract_checks(app_configs, **kwargs):
    """Keep the merged Internal Payroll domain company-owned and on the IMS identity model."""

    from django.apps import apps as django_apps
    from django.conf import settings

    issues = []
    if settings.AUTH_USER_MODEL != "accounts.User":
        issues.append(
            Error(
                "Internal Payroll must use the existing IMS accounts.User identity model.",
                id="payroll.E201",
            )
        )

    for model in django_apps.get_app_config("internal_payroll").get_models():
        if not any(field.name == "company" for field in model._meta.fields):
            issues.append(
                Error(
                    f"{model._meta.label} is missing direct company ownership.",
                    hint="Every Internal Payroll business record must remain inside the shared Company tenant boundary.",
                    id="payroll.E202",
                )
            )
    return issues
