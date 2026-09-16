from __future__ import annotations

from django.db.models import Count, Exists, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce

from ..models import (
    SourcingManpowerContact,
    SourcingMaterial,
    SourcingTrade,
    SourcingVendorContact,
    SourcingVendorOffer,
    SourcingWorkforceOffer,
)


def vendor_directory_scale_annotations(*, company, queryset, contact_query: str = ""):
    active_offer_count = (
        SourcingVendorOffer.objects.for_company(company)
        .filter(vendor_id=OuterRef("pk"), is_active=True)
        .values("vendor_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    active_contact_count = (
        SourcingVendorContact.objects.for_company(company)
        .filter(vendor_id=OuterRef("pk"), is_active=True)
        .values("vendor_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    queryset = queryset.annotate(
        supply_item_count=Coalesce(Subquery(active_offer_count, output_field=IntegerField()), Value(0)),
        contact_count=Coalesce(Subquery(active_contact_count, output_field=IntegerField()), Value(0)),
    )
    if contact_query:
        contact_match = SourcingVendorContact.objects.for_company(company).filter(
            vendor_id=OuterRef("pk"),
            is_active=True,
        ).filter(
            Q(first_name__icontains=contact_query)
            | Q(last_name__icontains=contact_query)
            | Q(email__icontains=contact_query)
            | Q(mobile__icontains=contact_query)
            | Q(work_phone__icontains=contact_query)
        )
        queryset = queryset.annotate(_contact_match=Exists(contact_match))
    return queryset


def manpower_directory_scale_annotations(*, company, queryset, contact_query: str = ""):
    active_offer_count = (
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(supplier_id=OuterRef("pk"), is_active=True)
        .values("supplier_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    active_contact_count = (
        SourcingManpowerContact.objects.for_company(company)
        .filter(supplier_id=OuterRef("pk"), is_active=True)
        .values("supplier_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    queryset = queryset.annotate(
        workforce_type_count=Coalesce(Subquery(active_offer_count, output_field=IntegerField()), Value(0)),
        contact_count=Coalesce(Subquery(active_contact_count, output_field=IntegerField()), Value(0)),
    )
    if contact_query:
        contact_match = SourcingManpowerContact.objects.for_company(company).filter(
            supplier_id=OuterRef("pk"),
            is_active=True,
        ).filter(
            Q(first_name__icontains=contact_query)
            | Q(last_name__icontains=contact_query)
            | Q(email__icontains=contact_query)
            | Q(mobile__icontains=contact_query)
            | Q(work_phone__icontains=contact_query)
        )
        queryset = queryset.annotate(_contact_match=Exists(contact_match))
    return queryset


def material_directory_scale_annotations(*, company, queryset):
    active_offer_count = (
        SourcingVendorOffer.objects.for_company(company)
        .filter(material_id=OuterRef("pk"), is_active=True)
        .values("material_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    active_vendor_count = (
        SourcingVendorOffer.objects.for_company(company)
        .filter(
            material_id=OuterRef("pk"),
            is_active=True,
            vendor__deleted_at__isnull=True,
            vendor__archived_at__isnull=True,
        )
        .values("material_id")
        .annotate(total=Count("vendor_id", distinct=True))
        .values("total")[:1]
    )
    return queryset.annotate(
        active_offer_count=Coalesce(Subquery(active_offer_count, output_field=IntegerField()), Value(0)),
        vendor_count=Coalesce(Subquery(active_vendor_count, output_field=IntegerField()), Value(0)),
    )


def trade_directory_scale_annotations(*, company, queryset):
    active_offer_count = (
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(trade_id=OuterRef("pk"), is_active=True)
        .values("trade_id")
        .annotate(total=Count("pk"))
        .values("total")[:1]
    )
    active_supplier_count = (
        SourcingWorkforceOffer.objects.for_company(company)
        .filter(
            trade_id=OuterRef("pk"),
            is_active=True,
            supplier__deleted_at__isnull=True,
            supplier__archived_at__isnull=True,
        )
        .values("trade_id")
        .annotate(total=Count("supplier_id", distinct=True))
        .values("total")[:1]
    )
    return queryset.annotate(
        active_offer_count=Coalesce(Subquery(active_offer_count, output_field=IntegerField()), Value(0)),
        supplier_count=Coalesce(Subquery(active_supplier_count, output_field=IntegerField()), Value(0)),
    )
