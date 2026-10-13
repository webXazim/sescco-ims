"""Small, controlled provider classification tags (independent from item categories)."""
from django.core.exceptions import ValidationError

SUGGESTED_PROVIDER_TAGS = (
    "Electrical", "Mechanical", "Civil", "Safety", "Instrumentation",
    "HVAC", "Piping", "Construction", "Maintenance", "IT", "Logistics",
)


def normalize_provider_tags(values):
    """Canonicalize free-form company tags before every model save.

    Data remains a short JSON list on the provider record; it never references
    another company or any operational Inventory/Payroll categories.
    """
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise ValidationError({"tags": "Tags must be a list of names."})
    cleaned, seen = [], set()
    for raw in values:
        if not isinstance(raw, str):
            raise ValidationError({"tags": "Every tag must be text."})
        name = " ".join(raw.split())
        if not name:
            continue
        if (len(name) > 40 or name.startswith(("=", "+", "-", "@")) or any(c in name for c in '"\\|<>[]{}')
                or any(ord(c) < 32 for c in name)):
            raise ValidationError({"tags": "Each tag must be 40 characters or fewer without special delimiters."})
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        common = next((tag for tag in SUGGESTED_PROVIDER_TAGS if tag.casefold() == key), None)
        cleaned.append(common or name)
        if len(cleaned) > 10:
            raise ValidationError({"tags": "A company can have no more than 10 tags."})
    return cleaned
