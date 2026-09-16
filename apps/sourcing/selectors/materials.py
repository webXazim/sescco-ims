from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q

from ..models import SourcingMaterial, SourcingVendorOffer
from .scale import material_directory_scale_annotations

PAGE_SIZES = (25, 50, 100)
ALLOWED_SORTS = {
    "name": "normalized_name",
    "code": "code",
    "category": "category",
    "updated": "updated_at",
}


@dataclass(frozen=True, slots=True)
class MaterialDirectoryResult:
    page_obj: object
    query: str
    status: str
    sort: str
    direction: str
    page_size: int


def _page_size(raw: object) -> int:
    try:
        value = int(str(raw or "50"))
    except ValueError:
        return 50
    return value if value in PAGE_SIZES else 50


def material_directory_page(*, company, params) -> MaterialDirectoryResult:
    query = str(params.get("q") or "").strip()[:160]
    status = str(params.get("status") or "active").strip().lower()
    if status not in {"active", "inactive", "all"}:
        status = "active"
    sort = str(params.get("sort") or "name").strip().lower()
    if sort not in ALLOWED_SORTS:
        sort = "name"
    direction = str(params.get("dir") or "asc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    page_size = _page_size(params.get("page_size"))

    qs = SourcingMaterial.objects.for_company(company)
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)

    if query:
        normalized_query = " ".join(query.split()).casefold()
        qs = qs.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(default_unit__icontains=query)
            | Q(normalized_aliases__icontains=normalized_query)
        )

    qs = material_directory_scale_annotations(company=company, queryset=qs)
    field = ALLOWED_SORTS[sort]
    order = f"-{field}" if direction == "desc" else field
    qs = qs.order_by(order, "pk")
    paginator = Paginator(qs, page_size)
    try:
        page_number = max(1, int(str(params.get("page") or "1")))
    except ValueError:
        page_number = 1
    page_obj = paginator.get_page(page_number)
    return MaterialDirectoryResult(
        page_obj=page_obj,
        query=query,
        status=status,
        sort=sort,
        direction=direction,
        page_size=page_size,
    )


def vendor_catalog(*, company, vendor):
    return list(
        SourcingVendorOffer.objects.for_company(company)
        .filter(vendor=vendor)
        .select_related("material", "verified_by")
        .order_by("-is_active", "material__category", "material__name", "specification", "brand", "model", "pk")
    )


def vendor_catalog_page(*, company, vendor, page=1, page_size=25):
    size = _page_size(page_size)
    queryset = (
        SourcingVendorOffer.objects.for_company(company)
        .filter(vendor=vendor)
        .select_related("material", "verified_by")
        .order_by("-is_active", "material__category", "material__name", "specification", "brand", "model", "pk")
    )
    paginator = Paginator(queryset, size)
    try:
        number = max(1, int(str(page or "1")))
    except ValueError:
        number = 1
    page_obj = paginator.get_page(number)
    return page_obj, list(page_obj.object_list), size
