from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditArea, AuditEvent

from ..models import SourcingEntityStatus, SourcingVendor
from .scale import vendor_directory_scale_annotations


ALLOWED_SORTS = {
    "name": "normalized_name",
    "code": "code",
    "city": "city",
    "updated": "updated_at",
    "verified": "last_verified_at",
}
PAGE_SIZES = (25, 50, 100)


@dataclass(frozen=True, slots=True)
class VendorDirectoryResult:
    page_obj: object
    query: str
    status: str
    sort: str
    direction: str
    page_size: int


def _bounded_page_size(raw: object) -> int:
    try:
        value = int(str(raw or "50"))
    except ValueError:
        return 50
    return value if value in PAGE_SIZES else 50


def vendor_directory_page(*, company, params) -> VendorDirectoryResult:
    query = str(params.get("q") or "").strip()[:160]
    status = str(params.get("status") or "active").strip().lower()
    if status not in {"active", "inactive", "archived", "trash", "all"}:
        status = "active"
    sort = str(params.get("sort") or "name").strip().lower()
    if sort not in ALLOWED_SORTS:
        sort = "name"
    direction = str(params.get("dir") or "asc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    page_size = _bounded_page_size(params.get("page_size"))

    qs = SourcingVendor.objects.for_company(company)
    if status == "trash":
        qs = qs.filter(deleted_at__isnull=False, purge_after__gt=timezone.now())
    else:
        qs = qs.filter(deleted_at__isnull=True)
        if status == "active":
            qs = qs.filter(archived_at__isnull=True, status=SourcingEntityStatus.ACTIVE)
        elif status == "inactive":
            qs = qs.filter(archived_at__isnull=True, status=SourcingEntityStatus.INACTIVE)
        elif status == "archived":
            qs = qs.filter(archived_at__isnull=False)

    qs = vendor_directory_scale_annotations(company=company, queryset=qs, contact_query=query)
    if query:
        qs = qs.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(display_name__icontains=query)
            | Q(primary_contact_name__icontains=query)
            | Q(phone__icontains=query)
            | Q(mobile__icontains=query)
            | Q(email__icontains=query)
            | Q(city__icontains=query)
            | Q(region__icontains=query)
            | Q(cr_number__icontains=query)
            | Q(vat_number__icontains=query)
            | Q(_contact_match=True)
        )

    field = ALLOWED_SORTS[sort]
    order = f"-{field}" if direction == "desc" else field
    qs = qs.order_by(order, "pk")

    paginator = Paginator(qs, page_size)
    try:
        page_number = max(1, int(str(params.get("page") or "1")))
    except ValueError:
        page_number = 1
    page_obj = paginator.get_page(page_number)
    return VendorDirectoryResult(
        page_obj=page_obj,
        query=query,
        status=status,
        sort=sort,
        direction=direction,
        page_size=page_size,
    )


def vendor_history(*, company, vendor, limit: int = 40):
    return list(
        AuditEvent.objects.filter(
            company=company,
            area=AuditArea.SOURCING,
            object_type="sourcing.SourcingVendor",
            object_id=str(vendor.pk),
        ).order_by("-created_at", "-id")[: max(1, min(limit, 100))]
    )
