from __future__ import annotations

import re
from collections.abc import Iterable

from django.db.models import F, Model, Q, QuerySet

from apps.explorer.filtering import resolve_date_range

from .models import StockItem, StockMovement
from .normalization import normalize_phone


LOW_STOCK_CONDITION = Q(current_quantity=0) | Q(
    minimum_quantity__gt=0,
    current_quantity__gt=0,
    current_quantity__lte=F("minimum_quantity"),
)


def stock_items() -> QuerySet[StockItem]:
    return StockItem.objects.select_related("project", "unit", "created_by", "updated_by")


def stock_movements() -> QuerySet[StockMovement]:
    return StockMovement.objects.select_related(
        "stock_item",
        "stock_item__project",
        "stock_item__unit",
        "created_by",
        "reversal_of",
        "reversal",
    )


def low_stock_items() -> QuerySet[StockItem]:
    return stock_items().filter(status=StockItem.Status.ACTIVE).filter(LOW_STOCK_CONDITION)


def apply_stock_status(queryset: QuerySet[StockItem], value: str) -> QuerySet[StockItem]:
    if value == "out":
        return queryset.filter(current_quantity=0)
    if value == "low":
        return queryset.filter(
            minimum_quantity__gt=0,
            current_quantity__gt=0,
            current_quantity__lte=F("minimum_quantity"),
        )
    if value == "in":
        return queryset.filter(current_quantity__gt=0).exclude(
            minimum_quantity__gt=0,
            current_quantity__lte=F("minimum_quantity"),
        )
    return queryset


def _search_terms(value: str) -> list[str]:
    return [term for term in re.split(r"\s+", value.strip()) if term]


def apply_stock_search(queryset: QuerySet[StockItem], value: str) -> QuerySet[StockItem]:
    """Apply AND-between-terms, OR-between-columns search."""
    for query in _search_terms(value):
        condition = (
            Q(project__code__icontains=query)
            | Q(project__name__icontains=query)
            | Q(project__client_name__icontains=query)
            | Q(project__location__icontains=query)
            | Q(material_name__icontains=query)
            | Q(description__icontains=query)
            | Q(supplier_name__icontains=query)
            | Q(supplier_phone__icontains=query)
            | Q(supplier_location__icontains=query)
            | Q(unit__name__icontains=query)
            | Q(unit__symbol__icontains=query)
            | Q(notes__icontains=query)
            | Q(created_by__username__icontains=query)
            | Q(created_by__first_name__icontains=query)
            | Q(created_by__last_name__icontains=query)
            | Q(updated_by__username__icontains=query)
            | Q(updated_by__first_name__icontains=query)
            | Q(updated_by__last_name__icontains=query)
        )
        phone_query = normalize_phone(query)
        if phone_query:
            condition |= Q(normalized_supplier_phone__icontains=phone_query)
        queryset = queryset.filter(condition)
    return queryset


def apply_movement_search(
    queryset: QuerySet[StockMovement], value: str
) -> QuerySet[StockMovement]:
    """Search immutable identity snapshots and current stock identity."""
    for query in _search_terms(value):
        condition = (
            Q(project_code_snapshot__icontains=query)
            | Q(project_name_snapshot__icontains=query)
            | Q(material_name_snapshot__icontains=query)
            | Q(supplier_name_snapshot__icontains=query)
            | Q(supplier_phone_snapshot__icontains=query)
            | Q(unit_symbol_snapshot__icontains=query)
            | Q(stock_item__project__code__icontains=query)
            | Q(stock_item__project__name__icontains=query)
            | Q(stock_item__project__client_name__icontains=query)
            | Q(stock_item__material_name__icontains=query)
            | Q(stock_item__description__icontains=query)
            | Q(stock_item__supplier_name__icontains=query)
            | Q(stock_item__supplier_phone__icontains=query)
            | Q(invoice_reference__icontains=query)
            | Q(purpose__icontains=query)
            | Q(recipient__icontains=query)
            | Q(reason__icontains=query)
            | Q(notes__icontains=query)
            | Q(created_by__username__icontains=query)
            | Q(created_by__first_name__icontains=query)
            | Q(created_by__last_name__icontains=query)
        )
        phone_query = normalize_phone(query)
        if phone_query:
            condition |= (
                Q(supplier_phone_normalized_snapshot__icontains=phone_query)
                | Q(stock_item__normalized_supplier_phone__icontains=phone_query)
            )
        queryset = queryset.filter(condition)
    return queryset


def _ids(values: Iterable[Model] | Model | None) -> list[int]:
    item_id = getattr(values, "pk", None)
    if item_id is not None:
        return [item_id]
    return [value.pk for value in values or []]


def filter_stock_items(queryset: QuerySet[StockItem], data: dict) -> QuerySet[StockItem]:
    queryset = apply_stock_search(queryset, data.get("q") or "")
    project_ids = _ids(data.get("project"))
    if project_ids:
        queryset = queryset.filter(project_id__in=project_ids)
    if data.get("project_status"):
        queryset = queryset.filter(project__status=data["project_status"])
    if data.get("material"):
        queryset = queryset.filter(material_name__icontains=data["material"].strip())
    if data.get("description"):
        queryset = queryset.filter(description__icontains=data["description"].strip())
    if data.get("supplier"):
        queryset = queryset.filter(supplier_name__icontains=data["supplier"].strip())
    if data.get("supplier_phone"):
        phone = normalize_phone(data["supplier_phone"])
        if phone:
            queryset = queryset.filter(normalized_supplier_phone__icontains=phone)
        else:
            queryset = queryset.none()
    if data.get("supplier_location"):
        queryset = queryset.filter(
            supplier_location__icontains=data["supplier_location"].strip()
        )
    unit_ids = _ids(data.get("unit"))
    if unit_ids:
        queryset = queryset.filter(unit_id__in=unit_ids)

    status = data.get("status") or StockItem.Status.ACTIVE
    if status in StockItem.Status.values:
        queryset = queryset.filter(status=status)
    elif status != "all":
        queryset = queryset.filter(status=StockItem.Status.ACTIVE)
    queryset = apply_stock_status(queryset, data.get("stock_status") or "")

    ranges = (
        ("quantity_min", "current_quantity__gte"),
        ("quantity_max", "current_quantity__lte"),
        ("minimum_min", "minimum_quantity__gte"),
        ("minimum_max", "minimum_quantity__lte"),
        ("price_min", "latest_unit_price__gte"),
        ("price_max", "latest_unit_price__lte"),
    )
    for key, lookup in ranges:
        if data.get(key) is not None:
            queryset = queryset.filter(**{lookup: data[key]})

    if data.get("created_by"):
        queryset = queryset.filter(created_by=data["created_by"])
    if data.get("updated_by"):
        queryset = queryset.filter(updated_by=data["updated_by"])

    date_range = resolve_date_range(
        data.get("date_preset") or "",
        start=data.get("date_from"),
        end=data.get("date_to"),
    )
    date_field = data.get("date_field") or "latest_addition_date"
    if date_field not in {"latest_addition_date", "created_at", "updated_at"}:
        date_field = "latest_addition_date"
    suffix = "__date" if date_field in {"created_at", "updated_at"} else ""
    if date_range.start:
        queryset = queryset.filter(**{f"{date_field}{suffix}__gte": date_range.start})
    if date_range.end:
        queryset = queryset.filter(**{f"{date_field}{suffix}__lte": date_range.end})
    return queryset


def filter_stock_movements(
    queryset: QuerySet[StockMovement], data: dict
) -> QuerySet[StockMovement]:
    queryset = apply_movement_search(queryset, data.get("q") or "")
    project_ids = _ids(data.get("project"))
    if project_ids:
        queryset = queryset.filter(stock_item__project_id__in=project_ids)
    if data.get("project_status"):
        queryset = queryset.filter(stock_item__project__status=data["project_status"])
    if data.get("material"):
        value = data["material"].strip()
        queryset = queryset.filter(
            Q(material_name_snapshot__icontains=value)
            | Q(stock_item__material_name__icontains=value)
        )
    if data.get("supplier"):
        value = data["supplier"].strip()
        queryset = queryset.filter(
            Q(supplier_name_snapshot__icontains=value)
            | Q(stock_item__supplier_name__icontains=value)
        )
    if data.get("supplier_phone"):
        phone = normalize_phone(data["supplier_phone"])
        if phone:
            queryset = queryset.filter(
                Q(supplier_phone_normalized_snapshot__icontains=phone)
                | Q(stock_item__normalized_supplier_phone__icontains=phone)
            )
        else:
            queryset = queryset.none()
    if data.get("movement_type"):
        queryset = queryset.filter(movement_type__in=data["movement_type"])
    if data.get("quantity_min") is not None:
        queryset = queryset.filter(quantity__gte=data["quantity_min"])
    if data.get("quantity_max") is not None:
        queryset = queryset.filter(quantity__lte=data["quantity_max"])
    if data.get("price_min") is not None:
        queryset = queryset.filter(unit_price__gte=data["price_min"])
    if data.get("price_max") is not None:
        queryset = queryset.filter(unit_price__lte=data["price_max"])
    if data.get("reference"):
        queryset = queryset.filter(invoice_reference__icontains=data["reference"].strip())
    if data.get("purpose"):
        queryset = queryset.filter(purpose__icontains=data["purpose"].strip())
    if data.get("recipient"):
        queryset = queryset.filter(recipient__icontains=data["recipient"].strip())
    if data.get("reason"):
        queryset = queryset.filter(reason__icontains=data["reason"].strip())
    if data.get("created_by"):
        queryset = queryset.filter(created_by=data["created_by"])

    date_range = resolve_date_range(
        data.get("date_preset") or "",
        start=data.get("date_from"),
        end=data.get("date_to"),
    )
    if date_range.start:
        queryset = queryset.filter(movement_date__gte=date_range.start)
    if date_range.end:
        queryset = queryset.filter(movement_date__lte=date_range.end)
    return queryset
