from __future__ import annotations

from dataclasses import dataclass

from django.db.models import QuerySet

from apps.projects.models import Project

from ..models import StockItem
from ..normalization import normalize_phone, normalize_text


@dataclass(frozen=True)
class StockMatchResult:
    exact: StockItem | None
    similar: QuerySet[StockItem]


def find_stock_matches(
    *,
    project: Project,
    material_name: str,
    supplier_name: str,
    supplier_phone: str,
    exclude_pk: int | None = None,
) -> StockMatchResult:
    base = StockItem.objects.select_related("project", "unit").filter(
        project=project, deleted_at__isnull=True, project__deleted_at__isnull=True
    )
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
