"""Company-scoped, paginated controlled service vocabulary browsing."""
from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator
from django.db.models import Count, Q

from ..models import SourcingService

PAGE_SIZES = (25, 50, 100)
SORTS = {"name": "normalized_name", "code": "code", "category": "category", "updated": "updated_at"}


@dataclass(frozen=True, slots=True)
class ServiceDirectoryResult:
    page_obj: object
    query: str
    status: str
    category: str
    sort: str
    direction: str
    page_size: int


def service_categories(company) -> list[str]:
    """Categories are reused only from the active company's service master."""
    values = SourcingService.objects.for_company(company).exclude(category="").values_list("category", flat=True)
    return sorted({value.strip() for value in values if value and value.strip()}, key=str.casefold)


def service_directory_page(*, company, params) -> ServiceDirectoryResult:
    query = str(params.get("q") or "").strip()[:160]
    status = str(params.get("status") or "active").strip().lower()
    if status not in {"active", "inactive", "all"}:
        status = "active"
    sort = str(params.get("sort") or "name").strip().lower()
    if sort not in SORTS:
        sort = "name"
    direction = str(params.get("dir") or "asc").strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    try:
        page_size = int(str(params.get("page_size") or "50"))
    except (ValueError, TypeError):
        page_size = 50
    if page_size not in PAGE_SIZES:
        page_size = 50
    category = str(params.get("category") or "").strip()[:120]

    qs = SourcingService.objects.for_company(company)
    if status != "all":
        qs = qs.filter(is_active=status == "active")
    if category:
        qs = qs.filter(category__iexact=category)
    if query:
        normalized = " ".join(query.split()).casefold()
        qs = qs.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(category__icontains=query)
            | Q(description__icontains=query)
            | Q(normalized_aliases__icontains=normalized)
        )
    # Related objects are counted only through the scoped service; relations are
    # isolated at model validation, and no company-foreign service is selectable.
    qs = qs.annotate(
        subcontractor_count=Count(
            "subcontractor_offers__subcontractor",
            filter=Q(subcontractor_offers__company=company, subcontractor_offers__subcontractor__company=company),
            distinct=True,
        ),
        active_offer_count=Count(
            "subcontractor_offers",
            filter=Q(subcontractor_offers__is_active=True, subcontractor_offers__company=company,
                     subcontractor_offers__subcontractor__company=company),
        ),
    )
    order_field = SORTS[sort]
    order = f"-{order_field}" if direction == "desc" else order_field
    paginator = Paginator(qs.order_by(order, "pk"), page_size)
    try:
        page_number = max(1, int(str(params.get("page") or "1")))
    except (ValueError, TypeError):
        page_number = 1
    return ServiceDirectoryResult(
        page_obj=paginator.get_page(page_number), query=query, status=status,
        category=category, sort=sort, direction=direction, page_size=page_size,
    )
