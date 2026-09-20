from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone

from ..freshness import (
    FRESHNESS_ALL,
    FRESHNESS_FRESH,
    FRESHNESS_NEEDS_VERIFICATION,
    FRESHNESS_NEVER,
    FRESHNESS_STALE,
    FRESHNESS_VALUES,
    freshness_age_days,
    freshness_key,
    freshness_label,
    sourcing_freshness_policy,
)
from ..models import SourcingAvailability, SourcingEntityStatus, SourcingMaterial, SourcingVendorOffer
from ..models.base import normalize_text

PAGE_SIZES = (25, 50, 100)
ALLOWED_SORTS = {
    "material": "material__normalized_name",
    "vendor": "vendor__normalized_name",
    "rate": "rate",
    "quantity": "available_quantity",
    "verified": "last_verified_at",
    "updated": "updated_at",
}
AVAILABILITY_VALUES = frozenset({"all", *(value for value, _label in SourcingAvailability.choices)})


@dataclass(frozen=True, slots=True)
class MaterialFinderResult:
    page_obj: object
    query: str
    availability: str
    freshness: str
    category: str
    vendor: str
    location: str
    rate_min: str
    rate_max: str
    sort: str
    direction: str
    page_size: int
    policy: object


def _page_size(raw: object) -> int:
    try:
        value = int(str(raw or "50"))
    except ValueError:
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
    if value < 0:
        return "", None
    return format(value, "f"), value


def material_finder_categories(*, company) -> list[str]:
    return list(
        SourcingMaterial.objects.for_company(company)
        .filter(is_active=True)
        .exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()[:200]
    )


def material_finder_page(*, company, params) -> MaterialFinderResult:
    query = str(params.get("q") or "").strip()[:160]
    availability = str(params.get("availability") or "all").strip().lower()
    if availability not in AVAILABILITY_VALUES:
        availability = "all"
    freshness = str(params.get("freshness") or FRESHNESS_ALL).strip().lower()
    if freshness not in FRESHNESS_VALUES:
        freshness = FRESHNESS_ALL
    category = str(params.get("category") or "").strip()[:120]
    vendor = str(params.get("vendor") or "").strip()[:160]
    location = str(params.get("location") or "").strip()[:160]
    rate_min_text, rate_min = _decimal_filter(params.get("rate_min"))
    rate_max_text, rate_max = _decimal_filter(params.get("rate_max"))
    if rate_min is not None and rate_max is not None and rate_max < rate_min:
        rate_min_text, rate_min, rate_max_text, rate_max = "", None, "", None

    sort = str(params.get("sort") or "material").strip().lower()
    if sort not in ALLOWED_SORTS:
        sort = "material"
    direction = str(params.get("dir") or ("desc" if sort == "verified" else "asc")).strip().lower()
    if direction not in {"asc", "desc"}:
        direction = "asc"
    page_size = _page_size(params.get("page_size"))
    policy = sourcing_freshness_policy(company=company)

    qs = (
        SourcingVendorOffer.objects.for_company(company)
        .filter(
            is_active=True,
            material__is_active=True,
            vendor__deleted_at__isnull=True,
            vendor__archived_at__isnull=True,
            vendor__status=SourcingEntityStatus.ACTIVE,
        )
        .select_related("vendor", "material", "verified_by")
    )

    if query:
        normalized_query = normalize_text(query)
        qs = qs.filter(
            Q(material__code__icontains=query)
            | Q(material__name__icontains=query)
            | Q(material__normalized_aliases__icontains=normalized_query)
            | Q(specification__icontains=query)
            | Q(brand__icontains=query)
            | Q(model__icontains=query)
            | Q(vendor__code__icontains=query)
            | Q(vendor__name__icontains=query)
            | Q(vendor__display_name__icontains=query)
        )
    if availability != "all":
        qs = qs.filter(availability=availability)
    if category:
        qs = qs.filter(material__category__iexact=category)
    if vendor:
        qs = qs.filter(
            Q(vendor__code__icontains=vendor)
            | Q(vendor__name__icontains=vendor)
            | Q(vendor__display_name__icontains=vendor)
        )
    if location:
        qs = qs.filter(Q(vendor__address__icontains=location) | Q(vendor__district__icontains=location) | Q(vendor__city__icontains=location) | Q(vendor__region__icontains=location) | Q(vendor__postal_code__icontains=location))
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

    field = ALLOWED_SORTS[sort]
    order = f"-{field}" if direction == "desc" else field
    secondary = "vendor__normalized_name" if sort != "vendor" else "material__normalized_name"
    qs = qs.order_by(order, secondary, "pk")

    paginator = Paginator(qs, page_size)
    try:
        page_number = max(1, int(str(params.get("page") or "1")))
    except ValueError:
        page_number = 1
    page_obj = paginator.get_page(page_number)

    today = timezone.localdate()
    for offer in page_obj.object_list:
        key = freshness_key(offer.last_verified_at, policy=policy, now=now)
        offer.finder_freshness_key = key
        offer.finder_freshness_label = freshness_label(key)
        offer.finder_age_days = freshness_age_days(offer.last_verified_at, now=now)
        offer.finder_has_quantity = offer.available_quantity is not None
        offer.finder_has_rate = offer.rate is not None
        offer.finder_rate_expired = bool(offer.rate_valid_until and offer.rate_valid_until < today)

    return MaterialFinderResult(
        page_obj=page_obj,
        query=query,
        availability=availability,
        freshness=freshness,
        category=category,
        vendor=vendor,
        location=location,
        rate_min=rate_min_text,
        rate_max=rate_max_text,
        sort=sort,
        direction=direction,
        page_size=page_size,
        policy=policy,
    )
