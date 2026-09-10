from django.apps import apps
from django.core.checks import Error, register


@register("merge")
def documents_merge_contract(app_configs, **kwargs):
    errors = []
    try:
        model = apps.get_model("documents", "BusinessDocument")
    except LookupError:
        return [Error("Payroll Documents app is not installed.", id="merge.E801")]

    if model._meta.db_table != "documents_business_document":
        errors.append(
            Error(
                "BusinessDocument database identity changed.",
                hint="Keep documents_business_document as the immutable payroll document table.",
                id="merge.E802",
            )
        )
    field_names = {field.name for field in model._meta.fields}
    required = {
        "company",
        "workspace",
        "document_type",
        "document_number",
        "source_model",
        "source_id",
        "snapshot",
        "source_fingerprint",
        "snapshot_fingerprint",
        "finalized_at",
    }
    missing = sorted(required - field_names)
    if missing:
        errors.append(Error(f"BusinessDocument is missing fields: {', '.join(missing)}", id="merge.E803"))
    return errors
