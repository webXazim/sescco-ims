"""Company-first sourcing search with correlated capability filters.

Filtering via one EXISTS avoids duplicates, N+1 queries and loading entire catalogs.
All capability and provider reads are explicitly tenant-scoped.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone

from ..freshness import (
    FRESHNESS_FRESH, FRESHNESS_NEEDS_VERIFICATION, FRESHNESS_STALE,
    FRESHNESS_NEVER, FRESHNESS_VALUES, sourcing_freshness_policy,
)
from ..models import (
    SourcingAvailability, SourcingVendorOffer, SourcingWorkforceOffer,
    SourcingSubcontractorService, SourcingServiceRateBasis, SourcingRateBasis,
)
from ..models.base import normalize_text

KINDS = {
    'vendor': (SourcingVendorOffer, 'vendor_id', 'material', 'material'),
    'manpower': (SourcingWorkforceOffer, 'supplier_id', 'trade', 'trade'),
    'subcontractor': (SourcingSubcontractorService, 'subcontractor_id', 'service', 'service'),
}
AVAILABILITIES = frozenset(x for x, _ in SourcingAvailability.choices)


def _decimal(value):
    value = str(value or '').strip()[:40]
    if not value:
        return ''
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError):
        return ''
    if not amount.is_finite() or amount < 0 or amount >= Decimal('100000000000000') or amount.as_tuple().exponent < -4:
        return ''
    return format(amount, 'f')


@dataclass(frozen=True)
class CapabilityFilters:
    category: str
    availability: str
    freshness: str
    location: str
    rate_min: str
    rate_max: str
    rate_basis: str
    active: bool


def parse_filters(*, kind, params):
    if kind not in KINDS:
        raise ValueError('Unsupported sourcing category')
    category = str(params.get('category') or '').strip()[:120]
    availability = str(params.get('availability') or 'all').strip().lower()
    if availability not in AVAILABILITIES:
        availability = 'all'
    freshness = str(params.get('freshness') or 'all').strip().lower()
    if freshness not in FRESHNESS_VALUES:
        freshness = 'all'
    location = str(params.get('location') or '').strip()[:120]
    rate_min = _decimal(params.get('rate_min'))
    rate_max = _decimal(params.get('rate_max'))
    if rate_min and rate_max and Decimal(rate_min) > Decimal(rate_max):
        rate_min = rate_max = ''
    rate_basis = str(params.get('rate_basis') or 'all').strip().lower()
    choices = {'manpower': set(SourcingRateBasis.values), 'subcontractor': set(SourcingServiceRateBasis.values)}
    # Only valid model-defined choices are accepted; categories with no rate basis omit it.
    if kind not in choices:
        rate_basis = 'all'
    elif rate_basis not in choices[kind]:
        rate_basis = 'all'
    return CapabilityFilters(
        category, availability, freshness, location, rate_min, rate_max,
        rate_basis,
        bool(category or availability != 'all' or freshness != 'all' or location or rate_min or rate_max or rate_basis != 'all'),
    )


def capability_queryset(*, company, kind, filters, provider_id=None, query='', include_provider_term=True):
    """One offer query; directory EXISTS and expanded row must use the same filters."""
    model, provider_fk, master_fk, _label = KINDS[kind]
    qs = model.objects.for_company(company).filter(is_active=True, **{
        f'{master_fk}__company': company, f'{master_fk}__is_active': True,
        f'{provider_fk[:-3]}__company': company,
    })
    if provider_id is not None:
        qs = qs.filter(**{provider_fk: provider_id})
    if filters.category:
        qs = qs.filter(**{f'{master_fk}__category__iexact': filters.category})
    if filters.availability != 'all':
        qs = qs.filter(availability=filters.availability)
    if filters.rate_min:
        qs = qs.filter(rate__gte=Decimal(filters.rate_min))
    if filters.rate_max:
        qs = qs.filter(rate__lte=Decimal(filters.rate_max))
    if filters.rate_basis != 'all':
        qs = qs.filter(rate_basis=filters.rate_basis)
    if filters.location:
        location = filters.location
        location_q = Q(**{f'{provider_fk[:-3]}__city__icontains': location}) | Q(**{f'{provider_fk[:-3]}__region__icontains': location})
        if kind == 'vendor':
            location_q |= Q(vendor__address__icontains=location) | Q(vendor__district__icontains=location)
        elif kind == 'manpower':
            location_q |= Q(work_location__icontains=location)
        else:
            location_q |= Q(service_location__icontains=location) | Q(subcontractor__service_coverage__icontains=location)
        qs = qs.filter(location_q)
    if filters.freshness != 'all':
        fresh, stale = sourcing_freshness_policy(company=company).cutoffs(now=timezone.now())
        if filters.freshness == FRESHNESS_FRESH:
            qs = qs.filter(last_verified_at__gte=fresh)
        elif filters.freshness == FRESHNESS_NEEDS_VERIFICATION:
            qs = qs.filter(last_verified_at__lt=fresh, last_verified_at__gte=stale)
        elif filters.freshness == FRESHNESS_STALE:
            qs = qs.filter(last_verified_at__lt=stale)
        elif filters.freshness == FRESHNESS_NEVER:
            qs = qs.filter(last_verified_at__isnull=True)
    if query:
        query = str(query).strip()[:160]
        normalized = normalize_text(query)
        conditions = (
            Q(**{f'{master_fk}__code__icontains': query})
            | Q(**{f'{master_fk}__name__icontains': query})
            | Q(**{f'{master_fk}__category__icontains': query})
            | Q(**{f'{master_fk}__normalized_aliases__icontains': normalized})
        )
        if kind == 'vendor':
            conditions |= Q(specification__icontains=query) | Q(brand__icontains=query) | Q(model__icontains=query)
        elif kind == 'manpower':
            conditions |= Q(work_location__icontains=query) | Q(mobilization_lead_time__icontains=query)
        else:
            conditions |= Q(scope_description__icontains=query) | Q(service_location__icontains=query) | Q(lead_time__icontains=query)
        if include_provider_term:
            conditions |= Q(**{f'{provider_fk[:-3]}__name__icontains': query}) | Q(**{f'{provider_fk[:-3]}__code__icontains': query})
        qs = qs.filter(conditions)
    return qs


def filter_company_capabilities(*, queryset, company, kind, params):
    """Filter on a SINGLE matching offer to avoid cross-offer false positives."""
    filters = parse_filters(kind=kind, params=params)
    if not filters.active:
        return queryset
    provider_fk = KINDS[kind][1]
    offers = capability_queryset(company=company, kind=kind, filters=filters, provider_id=OuterRef('pk'))
    return queryset.filter(Exists(offers))


def annotate_first_capability(*, queryset, company, kind, params):
    """One indexed subquery per displayed company, never an unbounded prefetch."""
    filters = parse_filters(kind=kind, params=params)
    provider_fk = KINDS[kind][1]
    master_fk = KINDS[kind][2]
    offers = capability_queryset(company=company, kind=kind, filters=filters, provider_id=OuterRef('pk'))
    offers = offers.order_by(f'{master_fk}__normalized_name', 'pk')
    return queryset.annotate(
        first_capability=Subquery(offers.values(f'{master_fk}__name')[:1]),
        first_capability_rate=Subquery(offers.values('rate')[:1]),
        first_capability_currency=Subquery(offers.values('currency')[:1]),
        first_capability_availability=Subquery(offers.values('availability')[:1]),
    )
