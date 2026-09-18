from __future__ import annotations

from dataclasses import dataclass
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
