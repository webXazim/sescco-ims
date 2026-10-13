"""Bounded, tenant-scoped subcontractor sourcing directory queries."""
from dataclasses import dataclass
from .unified import filter_company_capabilities, annotate_first_capability

from django.core.paginator import Paginator

from ..freshness import sourcing_freshness_policy, freshness_key, freshness_label
from django.db.models import Exists, OuterRef, Q, Count, Subquery, Value, IntegerField
from django.db.models.functions import Coalesce
from ..models.base import normalize_text
from django.utils import timezone

from apps.core.models import AuditArea, AuditEvent
from ..models import SourcingEntityStatus, SourcingSubcontractor, SourcingSubcontractorContact, SourcingSubcontractorVerificationRevision, SourcingSubcontractorService

PAGE_SIZES = (25, 50, 100)
SORTS = {"name": "normalized_name", "code": "code", "city": "city", "updated": "updated_at", "verified": "last_verified_at"}


@dataclass(frozen=True, slots=True)
class SubcontractorDirectoryResult:
    page_obj: object
    query: str
    status: str
    sort: str
    direction: str
    page_size: int


def subcontractor_directory_page(*, company, params):
    query = str(params.get("q") or "").strip()[:160]
    status = str(params.get("status") or "active").strip().lower()
    if status not in {"active", "inactive", "archived", "trash", "all"}:
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

    qs = SourcingSubcontractor.objects.for_company(company)
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
    contact_qs = SourcingSubcontractorContact.objects.for_company(company).filter(subcontractor_id=OuterRef("pk"))
    service_qs = SourcingSubcontractorService.objects.for_company(company).filter(subcontractor_id=OuterRef("pk"))
    contact_total = (contact_qs.order_by().values("subcontractor_id")
                     .annotate(total=Count("pk")).values("total")[:1])
    service_total = (service_qs.filter(is_active=True, service__is_active=True)
                     .order_by().values("subcontractor_id")
                     .annotate(total=Count("pk")).values("total")[:1])
    distinct_services = (service_qs.filter(is_active=True, service__is_active=True)
                         .order_by().values("subcontractor_id")
                         .annotate(total=Count("service_id", distinct=True)).values("total")[:1])
    qs = qs.annotate(
        contact_count=Coalesce(Subquery(contact_total, output_field=IntegerField()), Value(0)),
        active_service_count=Coalesce(Subquery(service_total, output_field=IntegerField()), Value(0)),
        active_service_type_count=Coalesce(Subquery(distinct_services, output_field=IntegerField()), Value(0)),
    )
    if query:
        normalized = normalize_text(query)
        qs = qs.annotate(
            contact_hit=Exists(contact_qs.filter(
                Q(first_name__icontains=query) | Q(last_name__icontains=query)
                | Q(email__icontains=query) | Q(mobile__icontains=query)
            )),
            service_hit=Exists(service_qs.filter(is_active=True, service__is_active=True).filter(
                Q(service__code__icontains=query) | Q(service__name__icontains=query)
                | Q(service__category__icontains=query)
                | Q(service__normalized_aliases__icontains=normalized)
                | Q(scope_description__icontains=query) | Q(service_location__icontains=query)
            )),
        ).filter(
            Q(code__icontains=query) | Q(name__icontains=query) | Q(display_name__icontains=query)
            | Q(primary_contact_name__icontains=query) | Q(company_phone__icontains=query)
            | Q(company_email__icontains=query) | Q(mobile__icontains=query) | Q(email__icontains=query)
            | Q(city__icontains=query) | Q(region__icontains=query) | Q(address__icontains=query)
            | Q(cr_number__icontains=query) | Q(vat_number__icontains=query)
            | Q(tags__icontains=query) | Q(service_coverage__icontains=query) | Q(contact_hit=True) | Q(service_hit=True)
        )
    tag = str(params.get("tag") or "").strip()[:40]
    if tag and '"' not in tag and "\\" not in tag:
        # Quoted match against the short JSON list avoids matching e.g. "Civil" inside "Civil Works".
        qs = qs.filter(tags__icontains='"' + tag + '"')

    qs = filter_company_capabilities(queryset=qs, company=company, kind='subcontractor', params=params)
    qs = annotate_first_capability(queryset=qs, company=company, kind='subcontractor', params=params)

    field = SORTS[sort]
    qs = qs.order_by(("-" if direction == "desc" else "") + field, "pk")
    paginator = Paginator(qs, page_size)
    try:
        page = max(1, int(str(params.get("page") or "1")))
    except (ValueError, TypeError):
        page = 1
    return SubcontractorDirectoryResult(paginator.get_page(page), query, status, sort, direction, page_size)


def subcontractor_history(*, company, subcontractor, limit=40):
    return list(AuditEvent.objects.filter(
        company=company, area=AuditArea.SOURCING,
    ).filter(
        Q(object_type="sourcing.SourcingSubcontractor", object_id=str(subcontractor.pk))
        | Q(object_type="sourcing.SourcingSubcontractorService", metadata__subcontractorId=str(subcontractor.pk))
    ).order_by("-created_at", "-id")[:max(1, min(limit, 100))])


def subcontractor_verification_page(*, company, subcontractor, page=1):
    queryset = (SourcingSubcontractorVerificationRevision.objects.for_company(company)
                .filter(subcontractor_id_snapshot=subcontractor.pk).select_related("actor")
                .order_by("-verified_at", "-created_at", "-pk"))
    return Paginator(queryset, 25).get_page(page)


def stamp_subcontractor_freshness(*, company, records):
    policy = sourcing_freshness_policy(company=company)
    for record in records:
        record.freshness_key = freshness_key(record.last_verified_at, policy=policy)
        record.freshness_label = freshness_label(record.freshness_key)
    return records
