from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import QueryDict

from .filtering import querydict_to_plain
from .models import SavedView


ALLOWED_PARAMS: dict[str, tuple[str, ...]] = {
    SavedView.ViewType.INVENTORY: (
        "q", "project", "project_status", "material", "description", "supplier",
        "supplier_phone", "supplier_location", "unit", "stock_status", "status",
        "quantity_min", "quantity_max", "minimum_min", "minimum_max", "price_min",
        "price_max", "date_field", "date_preset", "date_from", "date_to",
        "created_by", "updated_by", "sort", "columns",
    ),
    SavedView.ViewType.ACTIVITY: (
        "q", "project", "project_status", "material", "supplier", "supplier_phone",
        "movement_type", "quantity_min", "quantity_max", "price_min", "price_max",
        "reference", "purpose", "recipient", "reason", "created_by", "date_preset",
        "date_from", "date_to", "sort", "columns",
    ),
    SavedView.ViewType.LOW_STOCK: (
        "q", "project", "material", "supplier", "supplier_phone", "unit",
        "stock_status", "quantity_min", "quantity_max", "minimum_min", "minimum_max",
        "date_field", "date_preset", "date_from", "date_to", "sort", "columns",
    ),
}


def clean_saved_params(view_type: str, query: QueryDict) -> dict[str, str | list[str]]:
    allowed = ALLOWED_PARAMS.get(view_type)
    if not allowed:
        raise ValueError("Unsupported saved view type.")
    return querydict_to_plain(query, allowed)


def create_saved_view(*, owner, name: str, view_type: str, query: QueryDict) -> SavedView:
    params = clean_saved_params(view_type, query)
    try:
        with transaction.atomic():
            return SavedView.objects.create(
                owner=owner,
                name=name,
                view_type=view_type,
                query_params=params,
            )
    except (IntegrityError, ValidationError) as exc:
        raise ValueError("You already have a saved view with this name in this section.") from exc
