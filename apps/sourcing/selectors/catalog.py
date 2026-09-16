from __future__ import annotations

from dataclasses import dataclass

from django.core.paginator import Paginator

from ..models import SourcingVendorOfferRevision

PAGE_SIZES = (25, 50, 100)


@dataclass(frozen=True)
class OfferRevisionChange:
    label: str
    before: object
    after: object


REVISION_FIELDS = (
    ("availability", "Availability"),
    ("availableQuantity", "Available Qty"),
    ("unit", "Unit"),
    ("minimumQuantity", "Minimum Order Qty"),
    ("rate", "Reference Rate"),
    ("currency", "Currency"),
    ("rateValidUntil", "Rate Valid Until"),
    ("leadTime", "Lead Time"),
    ("verificationNote", "Verification Note"),
)


def _page_size(raw) -> int:
    try:
        value = int(raw or 25)
    except (TypeError, ValueError):
        return 25
    return value if value in PAGE_SIZES else 25


def _revision_changes(revision) -> list[OfferRevisionChange]:
    before = revision.before or {}
    after = revision.after or {}
    changes: list[OfferRevisionChange] = []
    for key, label in REVISION_FIELDS:
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes.append(OfferRevisionChange(label=label, before=old, after=new))
    return changes


def offer_revisions(*, company, offer, limit: int = 20):
    rows = list(
        SourcingVendorOfferRevision.objects.for_company(company)
        .filter(offer_id_snapshot=offer.pk)
        .select_related("actor")
        .order_by("-verified_at", "-created_at")[: max(1, min(limit, 100))]
    )
    for revision in rows:
        revision.display_changes = _revision_changes(revision)
    return rows


def offer_revision_page(*, company, offer, page=1, page_size=25):
    size = _page_size(page_size)
    queryset = (
        SourcingVendorOfferRevision.objects.for_company(company)
        .filter(offer_id_snapshot=offer.pk)
        .select_related("actor")
        .order_by("-verified_at", "-created_at")
    )
    paginator = Paginator(queryset, size)
    page_obj = paginator.get_page(page)
    entries = list(page_obj.object_list)
    for revision in entries:
        revision.display_changes = _revision_changes(revision)
    return page_obj, entries, size
