"""Bounded and company-isolated catalog/revision reads."""
from django.core.paginator import Paginator

from ..models import SourcingSubcontractorService, SourcingSubcontractorServiceRevision

PAGE_SIZES = (10, 25, 50, 100)
HISTORY_PAGE_SIZES = (25, 50, 100)


def _size(raw, choices, default):
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return default
    return parsed if parsed in choices else default


def catalog_page(*, company, subcontractor, page=1, page_size=10):
    queryset = (SourcingSubcontractorService.objects.for_company(company)
                .filter(subcontractor=subcontractor).select_related("service", "verified_by")
                .order_by("-is_active", "service__normalized_name", "scope_description", "pk"))
    return Paginator(queryset, _size(page_size, PAGE_SIZES, 10)).get_page(page)


def catalog_history_page(*, company, offer, page=1, page_size=25):
    queryset = (SourcingSubcontractorServiceRevision.objects.for_company(company)
                .filter(offer_id_snapshot=offer.pk).select_related("actor")
                .order_by("-verified_at", "-created_at", "-pk"))
    return Paginator(queryset, _size(page_size, HISTORY_PAGE_SIZES, 25)).get_page(page)
