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


def workforce_catalog(*, company, supplier):
    """Compatibility helper for focused callers; profile pages use the bounded paginator below."""
    return list(
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(supplier=supplier)
        .select_related("trade", "verified_by")
        .order_by("-is_active", "trade__category", "trade__name", "rate_basis", "pk")
    )


def workforce_catalog_page(*, company, supplier, page=1, page_size=25):
    size = _page_size(page_size)
    queryset = (
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(supplier=supplier)
        .select_related("trade", "verified_by")
        .order_by("-is_active", "trade__category", "trade__name", "rate_basis", "pk")
    )
    paginator = Paginator(queryset, size)
    try:
        number = max(1, int(str(page or "1")))
    except ValueError:
        number = 1
    page_obj = paginator.get_page(number)
    return page_obj, list(page_obj.object_list), size
