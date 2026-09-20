from __future__ import annotations

from dataclasses import dataclass
import re
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.core.models import AuditArea, AuditEvent


DELIVERY_SHARE_SALT = "sescco.documents.delivery-pack.v1"
DEFAULT_DELIVERY_SHARE_TTL_SECONDS = 30 * 24 * 60 * 60
DELIVERY_SHARE_REISSUED_ACTION = "documents.delivery_share_reissued"
DELIVERY_SHARE_REVOKED_ACTION = "documents.delivery_share_revoked"


SUPPLIER_DELIVERY_CONTRACT_VERSION = "2.0"
SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE = "receipt_only"
SUPPLIER_DELIVERY_PRIMARY_TYPE = "supplier_timesheet_pack"
SUPPLIER_DELIVERY_LEGACY_VARIANT = "supplier_timesheet"


def supplier_delivery_document_role(document) -> str:
    snapshot = document.__dict__.get("snapshot") or {}
    document_type = str(getattr(document, "document_type", "") or "").strip()
    if document_type == SUPPLIER_DELIVERY_PRIMARY_TYPE:
        return "supplier_timesheet_pack"
    if document_type == "rental_timesheet" and str(snapshot.get("document_variant") or "").strip() == SUPPLIER_DELIVERY_LEGACY_VARIANT:
        return "legacy_supplier_timesheet"
    if document_type == "supplier_settlement":
        return "supplier_settlement"
    if document_type == "supplier_payment_receipt":
        return "supplier_payment_advice"
    return ""


def supplier_delivery_document_label(document) -> str:
    return {
        "supplier_timesheet_pack": "Supplier Monthly Timesheet Pack",
        "legacy_supplier_timesheet": "Supplier Timesheet Statement (Legacy)",
        "supplier_settlement": "Supplier Settlement Statement",
        "supplier_payment_advice": "Supplier Payment Advice",
    }.get(supplier_delivery_document_role(document), str(getattr(document, "title", "") or "Document"))


def supplier_delivery_is_primary(document) -> bool:
    return supplier_delivery_document_role(document) == "supplier_timesheet_pack"


def _filename_token(value: object, *, fallback: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return token[:80] or fallback


def supplier_delivery_filename(document) -> str:
    snapshot = document.__dict__.get("snapshot") or {}
    supplier = snapshot.get("supplier") or {}
    project = snapshot.get("project") or {}
    supplier_code = _filename_token(supplier.get("code") or getattr(document, "entity_reference", ""), fallback="SUPPLIER")
    project_code = _filename_token(project.get("code"), fallback="ALL-PROJECTS")
    period_start = getattr(document, "period_start", None)
    period = period_start.strftime("%Y-%m") if period_start else "NO-PERIOD"
    role = supplier_delivery_document_role(document)
    role_token = {
        "supplier_timesheet_pack": "Supplier-Timesheet-Pack",
        "legacy_supplier_timesheet": "Supplier-Timesheet-Legacy",
        "supplier_settlement": "Settlement-Statement",
        "supplier_payment_advice": "Payment-Advice",
    }.get(role, "Supplier-Document")
    number = _filename_token(getattr(document, "document_number", ""), fallback="DOCUMENT")
    parts = ["SESCCO", supplier_code, project_code, period, role_token, number]
    return "_".join(parts) + ".pdf"


def supplier_delivery_manifest_entry(document) -> dict[str, object]:
    role = supplier_delivery_document_role(document)
    return {
        "id": str(document.id),
        "number": document.document_number,
        "type": str(document.document_type),
        "role": role,
        "label": supplier_delivery_document_label(document),
        "period": document.period_start.strftime("%Y-%m") if document.period_start else "",
        "source_reference": document.source_reference,
        "file_name": supplier_delivery_filename(document),
        "primary": role == "supplier_timesheet_pack",
    }


def prefer_v3_supplier_timesheets(documents):
    """Hide a legacy supplier-timesheet statement only when its exact locked source has a v3 pack.

    Historical legacy statements remain valid and deliverable when no replacement v3 pack exists.
    This avoids showing/sending two timesheet documents for the same supplier/project/month source.
    """
    rows = list(documents)
    v3_keys = {
        (str(getattr(row, "source_id", "")), str(getattr(row, "entity_reference", "") or "").strip().upper())
        for row in rows
        if supplier_delivery_document_role(row) == "supplier_timesheet_pack"
    }
    preferred = []
    for row in rows:
        role = supplier_delivery_document_role(row)
        key = (str(getattr(row, "source_id", "")), str(getattr(row, "entity_reference", "") or "").strip().upper())
        if role == "legacy_supplier_timesheet" and key in v3_keys:
            continue
        preferred.append(row)
    order = {
        "supplier_timesheet_pack": 0,
        "legacy_supplier_timesheet": 1,
        "supplier_settlement": 2,
        "supplier_payment_advice": 3,
    }
    return sorted(
        preferred,
        key=lambda row: (
            getattr(row, "period_start", None) or datetime.min.date(),
            order.get(supplier_delivery_document_role(row), 99),
            str(getattr(row, "source_reference", "") or ""),
            str(getattr(row, "document_number", "") or ""),
        ),
    )


@dataclass(frozen=True)
class DeliveryShare:
    pack: AuditEvent
    expires_at: object
    generation: int


def delivery_share_ttl_seconds() -> int:
    raw = getattr(settings, "DOCUMENT_DELIVERY_SHARE_TTL_SECONDS", DEFAULT_DELIVERY_SHARE_TTL_SECONDS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_DELIVERY_SHARE_TTL_SECONDS
    return max(3600, min(value, 90 * 24 * 60 * 60))


def delivery_share_generation(pack: AuditEvent) -> int:
    latest = AuditEvent.objects.filter(
        company=pack.company,
        area=AuditArea.DOCUMENTS,
        action=DELIVERY_SHARE_REISSUED_ACTION,
        object_type="documents.DocumentDeliveryPack",
        object_id=pack.object_id,
    ).order_by("-created_at", "-id").first()
    if latest is None:
        return 1
    try:
        return max(1, int((latest.metadata or {}).get("generation") or 1))
    except (TypeError, ValueError):
        return 1


def delivery_share_revoked_event(pack: AuditEvent, *, generation: int | None = None) -> AuditEvent | None:
    current_generation = generation or delivery_share_generation(pack)
    rows = AuditEvent.objects.filter(
        company=pack.company,
        area=AuditArea.DOCUMENTS,
        action=DELIVERY_SHARE_REVOKED_ACTION,
        object_type="documents.DocumentDeliveryPack",
        object_id=pack.object_id,
    ).order_by("-created_at", "-id")
    for event in rows[:20]:
        try:
            event_generation = int((event.metadata or {}).get("generation") or 1)
        except (TypeError, ValueError):
            event_generation = 1
        if event_generation == current_generation:
            return event
    return None


def delivery_share_is_revoked(pack: AuditEvent, *, generation: int | None = None) -> bool:
    return delivery_share_revoked_event(pack, generation=generation) is not None


def delivery_share_issued_at(pack: AuditEvent, *, generation: int | None = None):
    """Return the fixed start time for one share generation. Copying a link must not extend its lifetime."""
    current_generation = generation or delivery_share_generation(pack)
    if current_generation <= 1:
        return pack.created_at
    rows = AuditEvent.objects.filter(
        company=pack.company,
        area=AuditArea.DOCUMENTS,
        action=DELIVERY_SHARE_REISSUED_ACTION,
        object_type="documents.DocumentDeliveryPack",
        object_id=pack.object_id,
    ).order_by("-created_at", "-id")
    for event in rows[:20]:
        try:
            event_generation = max(1, int((event.metadata or {}).get("generation") or 1))
        except (TypeError, ValueError):
            event_generation = 1
        if event_generation == current_generation:
            return event.created_at
    return pack.created_at


def delivery_share_expires_at(pack: AuditEvent, *, generation: int | None = None):
    return delivery_share_issued_at(pack, generation=generation) + timedelta(seconds=delivery_share_ttl_seconds())


def delivery_share_is_expired(pack: AuditEvent, *, generation: int | None = None) -> bool:
    return timezone.now() >= delivery_share_expires_at(pack, generation=generation)


def make_delivery_share_token(pack: AuditEvent) -> str:
    generation = delivery_share_generation(pack)
    issued_at = delivery_share_issued_at(pack, generation=generation)
    payload = {
        "company": str(pack.company_id),
        "pack": str(pack.id),
        "object": str(pack.object_id),
        "generation": generation,
        "issued_at": int(issued_at.timestamp()),
    }
    return signing.dumps(payload, salt=DELIVERY_SHARE_SALT, compress=True)


def resolve_delivery_share(*, pack_event_id, token: str) -> DeliveryShare:
    try:
        # Expiry is enforced from the fixed generation start below. Using signer max_age here
        # would let every newly copied token silently restart the validity window.
        payload = signing.loads(token, salt=DELIVERY_SHARE_SALT)
    except signing.BadSignature as exc:
        raise PermissionDenied("This document link is invalid.") from exc
    try:
        pack = AuditEvent.objects.select_related("company").get(
            pk=pack_event_id,
            area=AuditArea.DOCUMENTS,
            action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack",
        )
    except AuditEvent.DoesNotExist as exc:
        raise PermissionDenied("This document pack is unavailable.") from exc
    if (
        str(payload.get("company") or "") != str(pack.company_id)
        or str(payload.get("pack") or "") != str(pack.id)
        or str(payload.get("object") or "") != str(pack.object_id)
    ):
        raise PermissionDenied("This document link is invalid.")
    try:
        token_generation = max(1, int(payload.get("generation") or 1))
    except (TypeError, ValueError) as exc:
        raise PermissionDenied("This document link is invalid.") from exc
    current_generation = delivery_share_generation(pack)
    if token_generation != current_generation:
        raise PermissionDenied("This document link has been replaced.")
    if delivery_share_is_revoked(pack, generation=current_generation):
        raise PermissionDenied("This document link has been revoked.")
    expected_issued_at = delivery_share_issued_at(pack, generation=current_generation)
    try:
        token_issued_at = datetime.fromtimestamp(int(payload.get("issued_at") or 0), tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        token_issued_at = expected_issued_at
    if token_issued_at.year < 2000:
        token_issued_at = expected_issued_at
    # New tokens bind to the immutable generation start. Legacy tokens remain valid only
    # until the earlier of their embedded issue time and the current generation expiry.
    issued_at = min(token_issued_at, expected_issued_at)
    expires_at = min(
        issued_at + timedelta(seconds=delivery_share_ttl_seconds()),
        delivery_share_expires_at(pack, generation=current_generation),
    )
    if timezone.now() >= expires_at:
        raise PermissionDenied("This document link has expired.")
    return DeliveryShare(pack=pack, expires_at=expires_at, generation=current_generation)
