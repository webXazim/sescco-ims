from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q, QuerySet

from apps.projects.models import Project

from ..models import InventoryLocation, StockItem
from ..normalization import normalize_phone, normalize_text


@dataclass(frozen=True)
class StockMatchResult:
    exact: StockItem | None
    similar: QuerySet[StockItem]


def find_stock_matches(
    *,
    project: Project | None = None,
    location: InventoryLocation | None = None,
    material_name: str,
    supplier_name: str,
    supplier_phone: str,
    condition: str = StockItem.Condition.NEW,
    exclude_pk: int | None = None,
) -> StockMatchResult:
    if location is None:
        if project is None:
            raise ValueError("A project or inventory location is required for stock matching.")
        location = project.inventory_location
    elif project is not None and location.project_id != project.pk:
        raise ValueError("Project and inventory location do not match.")
    base = StockItem.objects.for_company(location.company).select_related("project", "unit").filter(
        location=location,
        condition=condition,
        deleted_at__isnull=True,
    ).filter(Q(project__isnull=True) | Q(project__deleted_at__isnull=True))
    if exclude_pk:
        base = base.exclude(pk=exclude_pk)

    normalized_material = normalize_text(material_name)
    normalized_supplier = normalize_text(supplier_name)
    normalized_phone = normalize_phone(supplier_phone)

    exact = base.filter(
        normalized_material_name=normalized_material,
        normalized_supplier_name=normalized_supplier,
        normalized_supplier_phone=normalized_phone,
    ).first()

    similar = base.none()
    if normalized_material and normalized_supplier:
        similar = base.filter(
            normalized_material_name=normalized_material,
            normalized_supplier_name=normalized_supplier,
        ).exclude(normalized_supplier_phone=normalized_phone)

    return StockMatchResult(exact=exact, similar=similar.order_by("supplier_phone")[:5])
