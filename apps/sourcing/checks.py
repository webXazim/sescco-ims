from __future__ import annotations

from django.apps import apps
from django.core.checks import Error, Tags, register


from .isolation import FORBIDDEN_OPERATIONAL_APP_LABELS
ALLOWED_RELATION_APP_LABELS = frozenset({"accounts", "core", "sourcing"})


@register(Tags.models)
def sourcing_domain_isolation_check(app_configs, **kwargs):
    """Fail deployment if Sourcing gains a database relation to an operational domain.

    Sourcing is intentionally a call-list/reference directory. A future developer must
    not quietly turn a sourcing Vendor/Workforce record into Inventory, Payroll,
    Projects, Documents or Data Exchange authority by adding a foreign key.
    """

    errors = []
    sourcing_config = apps.get_app_config("sourcing")
    for model in sourcing_config.get_models():
        for field in model._meta.get_fields():
            remote_model = getattr(getattr(field, "remote_field", None), "model", None)
            remote_meta = getattr(remote_model, "_meta", None)
            if remote_meta is None:
                continue
            target_app = remote_meta.app_label
            if target_app in FORBIDDEN_OPERATIONAL_APP_LABELS:
                errors.append(
                    Error(
                        f"{model._meta.label}.{field.name} links Sourcing to operational app {target_app!r}.",
                        hint="Sourcing may relate only to core/accounts/sourcing records; copy reference data into operational transactions instead.",
                        obj=field,
                        id="sourcing.E001",
                    )
                )
            elif target_app not in ALLOWED_RELATION_APP_LABELS:
                errors.append(
                    Error(
                        f"{model._meta.label}.{field.name} links Sourcing to unapproved app {target_app!r}.",
                        hint="Extend the Sourcing isolation contract explicitly before adding cross-app relations.",
                        obj=field,
                        id="sourcing.E002",
                    )
                )
    return errors
