from __future__ import annotations

from django.core.paginator import Paginator

from ..models import SourcingWorkforceOffer

PAGE_SIZES = (25, 50, 100)


def _page_size(raw: object) -> int:
    try:
        value = int(str(raw or "25"))
    except ValueError:
        return 25
    return value if value in PAGE_SIZES else 25


OVERVIEW_PREVIEW_LIMIT = 5


def _workforce_catalog_queryset(*, company, supplier):
    return (
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(supplier=supplier)
        .select_related("trade", "verified_by")
        .order_by("-is_active", "trade__category", "trade__name", "rate_basis", "pk")
    )


def workforce_catalog(*, company, supplier):
    """Compatibility helper for focused callers; profile pages use the bounded paginator below."""
    return list(_workforce_catalog_queryset(company=company, supplier=supplier))


def workforce_catalog_overview(*, company, supplier, limit: int = OVERVIEW_PREVIEW_LIMIT):
    """Return a small, deterministic workforce preview for the Supplier Overview panel."""
    try:
        requested_limit = int(limit or OVERVIEW_PREVIEW_LIMIT)
    except (TypeError, ValueError):
        requested_limit = OVERVIEW_PREVIEW_LIMIT
    bounded_limit = max(1, min(requested_limit, 10))
    return list(_workforce_catalog_queryset(company=company, supplier=supplier)[:bounded_limit])


def workforce_catalog_page(*, company, supplier, page=1, page_size=25):
    size = _page_size(page_size)
    queryset = _workforce_catalog_queryset(company=company, supplier=supplier)
    paginator = Paginator(queryset, size)
    try:
        number = max(1, int(str(page or "1")))
    except ValueError:
        number = 1
    page_obj = paginator.get_page(number)
    return page_obj, list(page_obj.object_list), size
