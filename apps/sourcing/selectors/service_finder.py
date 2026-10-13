"""Read-only, bounded, tenant-isolated subcontracted Service Finder.

Displays live service references, not quotes, purchase orders or reservations.
Verification status is derived from the existing company sourcing freshness policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from ..freshness import (
    FRESHNESS_ALL, FRESHNESS_FRESH, FRESHNESS_NEEDS_VERIFICATION,
    FRESHNESS_STALE, FRESHNESS_NEVER, FRESHNESS_VALUES,
    freshness_age_days, freshness_key, freshness_label, sourcing_freshness_policy,
)
from ..models import (
    SourcingAvailability, SourcingEntityStatus, SourcingService,
    SourcingServiceRateBasis, SourcingSubcontractorService,
)
from ..models.base import normalize_text

PAGE_SIZES = (25, 50, 100)
SORT_FIELDS = {
    "service": "service__normalized_name",
    "subcontractor": "subcontractor__normalized_name",
    "rate": "rate",
    "verified": "last_verified_at",
    "updated": "updated_at",
}
AVAILABILITY_VALUES = frozenset({"all", *(value for value, _ in SourcingAvailability.choices)})
RATE_BASIS_VALUES = frozenset({"all", *SourcingServiceRateBasis.values})


@dataclass(frozen=True, slots=True)
class ServiceFinderResult:
    page_obj: object
    query: str
    availability: str
    freshness: str
    category: str
    subcontractor: str
    location: str
    rate_basis: str
    currency: str
    rate_min: str
    rate_max: str
    sort: str
    direction: str
    page_size: int
    policy: object


def _page_size(raw: object) -> int:
    try:
        value = int(str(raw or "50"))
    except (ValueError, TypeError):
        return 50
    return value if value in PAGE_SIZES else 50


def _decimal_filter(raw: object) -> tuple[str, Decimal | None]:
    text = str(raw or "").strip()[:40]
    if not text:
        return "", None
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        return "", None
    # No NaN, Infinity, negatives or values outside the offer rate's 18,4 field.
    if not value.is_finite() or value < 0 or value >= Decimal("100000000000000"):
        return "", None
    if value == 0:
        return "0", Decimal(0)
    # Reject excess fractional precision and giant negative exponents rather than
    # allocating a massive fixed-point string for e.g. a 1e-999999999 input.
    if value.as_tuple().exponent < -4:
        return "", None
    return format(value, "f"), value


def service_finder_categories(*, company) -> list[str]:
    return list(
        SourcingService.objects.for_company(company)
        .filter(is_active=True).exclude(category="")
        .order_by("category").values_list("category", flat=True).distinct()[:200]
    )


def service_finder_page(*, company, params) -> ServiceFinderResult:
    query = str(params.get("q") or "").strip()[:160]
    availability = str(params.get("availability") or "all").strip().lower()
    if availability not in AVAILABILITY_VALUES:
        availability = "all"
    freshness = str(params.get("freshness") or FRESHNESS_ALL).strip().lower()
    if freshness not in FRESHNESS_VALUES:
        freshness = FRESHNESS_ALL
    category = str(params.get("category") or "").strip()[:120]
    subcontractor = str(params.get("subcontractor") or "").strip()[:160]
    location = str(params.get("location") or "").strip()[:160]
    rate_basis = str(params.get("rate_basis") or "all").strip().lower()
    if rate_basis not in RATE_BASIS_VALUES:
        rate_basis = "all"
    currency = str(params.get("currency") or "").strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        currency = ""
    rate_min_text, rate_min = _decimal_filter(params.get("rate_min"))
    rate_max_text, rate_max = _decimal_filter(params.get("rate_max"))
    if rate_min is not None and rate_max is not None and rate_min > rate_max:
        rate_min_text, rate_min, rate_max_text, rate_max = "", None, "", None

    sort = str(params.get("sort") or "service").strip().lower()
    if sort not in SORT_FIELDS:
        sort = "service"
    direction = str(params.get("dir") or ("desc" if sort == "verified" else "asc")).strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    page_size = _page_size(params.get("page_size"))
    policy = sourcing_freshness_policy(company=company)

    qs = (
        SourcingSubcontractorService.objects.for_company(company)
        .filter(
            is_active=True,
            service__company=company,
            service__is_active=True,
            subcontractor__company=company,
            subcontractor__status=SourcingEntityStatus.ACTIVE,
            subcontractor__archived_at__isnull=True,
            subcontractor__deleted_at__isnull=True,
        )
        .select_related("service", "subcontractor", "verified_by")
    )
    if query:
        normalized = normalize_text(query)
        qs = qs.filter(
            Q(service__code__icontains=query)
            | Q(service__name__icontains=query)
            | Q(service__category__icontains=query)
            | Q(service__normalized_aliases__icontains=normalized)
            | Q(scope_description__icontains=query)
            | Q(service_location__icontains=query)
            | Q(lead_time__icontains=query)
            | Q(subcontractor__code__icontains=query)
            | Q(subcontractor__name__icontains=query)
            | Q(subcontractor__display_name__icontains=query)
        )
    if availability != "all":
        qs = qs.filter(availability=availability)
    if category:
        qs = qs.filter(service__category__iexact=category)
    if subcontractor:
        qs = qs.filter(
            Q(subcontractor__code__icontains=subcontractor)
            | Q(subcontractor__name__icontains=subcontractor)
            | Q(subcontractor__display_name__icontains=subcontractor)
        )
    if location:
        qs = qs.filter(
            Q(service_location__icontains=location)
            | Q(subcontractor__service_coverage__icontains=location)
            | Q(subcontractor__city__icontains=location)
            | Q(subcontractor__region__icontains=location)
            | Q(subcontractor__district__icontains=location)
            | Q(subcontractor__address__icontains=location)
        )
    if rate_basis != "all":
        qs = qs.filter(rate_basis=rate_basis)
    if currency:
        qs = qs.filter(currency__iexact=currency)
    if rate_min is not None:
        qs = qs.filter(rate__gte=rate_min)
    if rate_max is not None:
        qs = qs.filter(rate__lte=rate_max)

    now = timezone.now()
    fresh_cutoff, stale_cutoff = policy.cutoffs(now=now)
    if freshness == FRESHNESS_FRESH:
        qs = qs.filter(last_verified_at__gte=fresh_cutoff)
    elif freshness == FRESHNESS_NEEDS_VERIFICATION:
        qs = qs.filter(last_verified_at__lt=fresh_cutoff, last_verified_at__gte=stale_cutoff)
    elif freshness == FRESHNESS_STALE:
        qs = qs.filter(last_verified_at__lt=stale_cutoff)
    elif freshness == FRESHNESS_NEVER:
        qs = qs.filter(last_verified_at__isnull=True)

    ordering = f"-{SORT_FIELDS[sort]}" if direction == "desc" else SORT_FIELDS[sort]
    secondary = "subcontractor__normalized_name" if sort != "subcontractor" else "service__normalized_name"
    qs = qs.order_by(ordering, secondary, "pk")
    paginator = Paginator(qs, page_size)
    try:
        requested_page = max(1, int(str(params.get("page") or "1")))
    except (ValueError, TypeError):
        requested_page = 1
    page_obj = paginator.get_page(requested_page)
    today = timezone.localdate()
    for offer in page_obj.object_list:
        key = freshness_key(offer.last_verified_at, policy=policy, now=now)
        offer.finder_freshness_key = key
        offer.finder_freshness_label = freshness_label(key)
        offer.finder_age_days = freshness_age_days(offer.last_verified_at, now=now)
        offer.finder_has_rate = offer.rate is not None
        offer.finder_rate_expired = bool(offer.rate_valid_until and offer.rate_valid_until < today)

    return ServiceFinderResult(
        page_obj=page_obj, query=query, availability=availability,
        freshness=freshness, category=category, subcontractor=subcontractor,
        location=location, rate_basis=rate_basis, currency=currency,
        rate_min=rate_min_text, rate_max=rate_max_text, sort=sort,
        direction=direction, page_size=page_size, policy=policy,
    )
