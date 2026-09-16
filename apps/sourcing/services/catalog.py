from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from ..models import (
    SourcingMaterial,
    SourcingVendor,
    SourcingVendorOffer,
    SourcingVendorOfferRevision,
)


def suggest_material_code() -> str:
    return f"MAT-{uuid4().hex[:8].upper()}"


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _date(value) -> str | None:
    return value.isoformat() if value else None


def _material_snapshot(material: SourcingMaterial) -> dict[str, object]:
    return {
        "code": material.code,
        "name": material.name,
        "category": material.category,
        "defaultUnit": material.default_unit,
        "aliases": list(material.aliases or []),
        "notes": material.notes,
        "isActive": material.is_active,
    }


def _offer_snapshot(offer: SourcingVendorOffer) -> dict[str, object]:
    return {
        "offerId": str(offer.pk),
        "vendorId": str(offer.vendor_id),
        "materialId": str(offer.material_id),
        "materialCode": offer.material.code if offer.material_id else None,
        "materialName": offer.material.name if offer.material_id else None,
        "specification": offer.specification,
        "brand": offer.brand,
        "model": offer.model,
        "availableQuantity": _decimal(offer.available_quantity),
        "unit": offer.unit,
        "minimumQuantity": _decimal(offer.minimum_quantity),
        "availability": offer.availability,
        "rate": _decimal(offer.rate),
        "currency": offer.currency,
        "rateValidUntil": _date(offer.rate_valid_until),
        "leadTime": offer.lead_time,
        "lastVerifiedAt": _date(offer.last_verified_at),
        "verifiedById": str(offer.verified_by_id) if offer.verified_by_id else None,
        "verificationNote": offer.verification_note,
        "notes": offer.notes,
        "isActive": offer.is_active,
    }


def _audit_material(*, material, actor_membership, action: str, before=None, after=None, request=None):
    return record_audit_event(
        company=material.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingMaterial",
        object_id=material.pk,
        object_label=f"{material.code} · {material.name}",
        actor_membership=actor_membership,
        before=before,
        after=after,
        request=request,
    )


def _audit_offer(*, offer, actor_membership, action: str, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=offer.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingVendorOffer",
        object_id=offer.pk,
        object_label=f"{offer.vendor.display_name or offer.vendor.name} · {offer.material.name}",
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


def _record_offer_revision(*, offer, actor_membership, before, after, contact_name: str, note: str):
    return SourcingVendorOfferRevision.objects.create(
        company=offer.company,
        offer=offer,
        offer_id_snapshot=offer.pk,
        vendor_id_snapshot=offer.vendor_id,
        material_id_snapshot=offer.material_id,
        before=before or {},
        after=after or {},
        verified_at=timezone.now(),
        actor=actor_membership.user,
        contact_name=str(contact_name or "").strip()[:160],
        note=str(note or "").strip()[:500],
    )


def _usable_vendor(*, company, vendor_id) -> SourcingVendor:
    vendor = (
        SourcingVendor.objects.select_for_update()
        .for_company(company)
        .get(pk=vendor_id, deleted_at__isnull=True)
    )
    if vendor.archived_at:
        raise ValidationError("Restore the archived Vendor before changing its Supply Catalog.")
    return vendor


@transaction.atomic
def create_material(*, actor_membership, cleaned_data: dict[str, object], request=None) -> SourcingMaterial:
    data = dict(cleaned_data)
    if not str(data.get("code") or "").strip():
        data["code"] = suggest_material_code()
    material = SourcingMaterial(company=actor_membership.company, **data)
    material.save()
    _audit_material(
        material=material,
        actor_membership=actor_membership,
        action="sourcing.material.created",
        after=_material_snapshot(material),
        request=request,
    )
    return material


@transaction.atomic
def update_material(*, actor_membership, material_id, cleaned_data: dict[str, object], request=None) -> SourcingMaterial:
    material = (
        SourcingMaterial.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=material_id)
    )
    before = _material_snapshot(material)
    for field, value in cleaned_data.items():
        setattr(material, field, value)
    material.save()
    _audit_material(
        material=material,
        actor_membership=actor_membership,
        action="sourcing.material.updated",
        before=before,
        after=_material_snapshot(material),
        request=request,
    )
    return material


@transaction.atomic
def set_material_active(*, actor_membership, material_id, is_active: bool, request=None) -> SourcingMaterial:
    material = (
        SourcingMaterial.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=material_id)
    )
    before = _material_snapshot(material)
    material.is_active = bool(is_active)
    material.save(update_fields=["is_active", "updated_at"])
    _audit_material(
        material=material,
        actor_membership=actor_membership,
        action="sourcing.material.activated" if material.is_active else "sourcing.material.deactivated",
        before=before,
        after=_material_snapshot(material),
        request=request,
    )
    return material


@transaction.atomic
def create_vendor_offer(
    *, actor_membership, vendor_id, cleaned_data: dict[str, object], verified_now: bool, contact_name: str = "", request=None
) -> SourcingVendorOffer:
    vendor = _usable_vendor(company=actor_membership.company, vendor_id=vendor_id)
    data = dict(cleaned_data)
    material = data.get("material")
    if not isinstance(material, SourcingMaterial) or material.company_id != vendor.company_id:
        raise ValidationError({"material": "Choose a Sourcing Material from this company."})
    if not material.is_active:
        raise ValidationError({"material": "Inactive Sourcing Materials cannot be added to a new Vendor offer."})

    offer = SourcingVendorOffer(company=vendor.company, vendor=vendor, **data)
    if verified_now:
        offer.last_verified_at = timezone.now()
        offer.verified_by = actor_membership.user
    offer.save()
    after = _offer_snapshot(offer)
    _record_offer_revision(
        offer=offer,
        actor_membership=actor_membership,
        before={},
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )
    if verified_now:
        vendor.last_verified_at = offer.last_verified_at
        vendor.save(update_fields=["last_verified_at", "updated_at"])
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.vendor_offer.created",
        after=after,
        metadata={"verifiedNow": bool(verified_now), "contactName": str(contact_name or "").strip()[:160]},
        request=request,
    )
    return offer


@transaction.atomic
def update_vendor_offer(
    *, actor_membership, vendor_id, offer_id, cleaned_data: dict[str, object], verified_now: bool, contact_name: str = "", request=None
) -> SourcingVendorOffer:
    vendor = _usable_vendor(company=actor_membership.company, vendor_id=vendor_id)
    offer = (
        SourcingVendorOffer.objects.select_for_update()
        .select_related("material", "vendor")
        .for_company(vendor.company)
        .get(pk=offer_id, vendor=vendor)
    )
    before = _offer_snapshot(offer)
    data = dict(cleaned_data)
    material = data.get("material")
    if not isinstance(material, SourcingMaterial) or material.company_id != vendor.company_id:
        raise ValidationError({"material": "Choose a Sourcing Material from this company."})
    if material.pk != offer.material_id and not material.is_active:
        raise ValidationError({"material": "Inactive Sourcing Materials cannot be assigned to an offer."})
    for field, value in data.items():
        setattr(offer, field, value)
    if verified_now:
        offer.last_verified_at = timezone.now()
        offer.verified_by = actor_membership.user
    offer.save()
    after = _offer_snapshot(offer)
    _record_offer_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )
    if verified_now:
        vendor.last_verified_at = offer.last_verified_at
        vendor.save(update_fields=["last_verified_at", "updated_at"])
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.vendor_offer.updated",
        before=before,
        after=after,
        metadata={"verifiedNow": bool(verified_now), "contactName": str(contact_name or "").strip()[:160]},
        request=request,
    )
    return offer


@transaction.atomic
def set_vendor_offer_active(*, actor_membership, vendor_id, offer_id, is_active: bool, request=None) -> SourcingVendorOffer:
    vendor = _usable_vendor(company=actor_membership.company, vendor_id=vendor_id)
    offer = (
        SourcingVendorOffer.objects.select_for_update()
        .select_related("material", "vendor")
        .for_company(vendor.company)
        .get(pk=offer_id, vendor=vendor)
    )
    before = _offer_snapshot(offer)
    offer.is_active = bool(is_active)
    offer.save(update_fields=["is_active", "updated_at"])
    after = _offer_snapshot(offer)
    _record_offer_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name="",
        note="Offer reactivated" if offer.is_active else "Offer deactivated",
    )
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.vendor_offer.activated" if offer.is_active else "sourcing.vendor_offer.deactivated",
        before=before,
        after=after,
        request=request,
    )
    return offer

@transaction.atomic
def verify_vendor_offer(
    *,
    actor_membership,
    vendor_id,
    offer_id,
    cleaned_data: dict[str, object],
    contact_name: str = "",
    request=None,
) -> SourcingVendorOffer:
    """Confirm the current sourcing quantity/rate without editing offer identity.

    This is deliberately reference-only: it updates the current SourcingVendorOffer
    snapshot and appends immutable verification evidence. It never creates stock,
    purchasing, payroll or accounting records.
    """
    vendor = _usable_vendor(company=actor_membership.company, vendor_id=vendor_id)
    offer = (
        SourcingVendorOffer.objects.select_for_update()
        .select_related("material", "vendor")
        .for_company(vendor.company)
        .get(pk=offer_id, vendor=vendor)
    )
    if not offer.is_active:
        raise ValidationError("Reactivate this Supply Catalog item before verifying it.")

    allowed_fields = {
        "availability",
        "available_quantity",
        "unit",
        "minimum_quantity",
        "rate",
        "currency",
        "rate_valid_until",
        "lead_time",
        "verification_note",
    }
    before = _offer_snapshot(offer)
    for field, value in cleaned_data.items():
        if field in allowed_fields:
            setattr(offer, field, value)

    verified_at = timezone.now()
    offer.last_verified_at = verified_at
    offer.verified_by = actor_membership.user
    offer.save()
    after = _offer_snapshot(offer)

    contact_name = str(contact_name or "").strip()[:160]
    _record_offer_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )

    vendor.last_verified_at = verified_at
    vendor.save(update_fields=["last_verified_at", "updated_at"])

    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.vendor_offer.verified",
        before=before,
        after=after,
        metadata={
            "contactName": contact_name,
            "verificationNote": offer.verification_note,
            "quickVerification": True,
        },
        request=request,
    )
    return offer
