from __future__ import annotations

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from ..models import (
    SourcingManpowerSupplier,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingWorkforceOfferRevision,
)


def suggest_trade_code() -> str:
    return f"TRD-{uuid4().hex[:8].upper()}"


def _trade_snapshot(trade: SourcingTrade) -> dict[str, object]:
    return {
        "code": trade.code,
        "name": trade.name,
        "category": trade.category,
        "aliases": list(trade.aliases or []),
        "isActive": trade.is_active,
    }


def _offer_snapshot(offer: SourcingWorkforceOffer) -> dict[str, object]:
    return {
        "supplierId": str(offer.supplier_id),
        "tradeId": str(offer.trade_id),
        "tradeCode": offer.trade.code,
        "tradeName": offer.trade.name,
        "availability": offer.availability,
        "availableQuantity": offer.available_quantity,
        "rate": str(offer.rate) if offer.rate is not None else None,
        "currency": offer.currency,
        "rateBasis": offer.rate_basis,
        "overtimeRate": str(offer.overtime_rate) if offer.overtime_rate is not None else None,
        "rateValidUntil": offer.rate_valid_until.isoformat() if offer.rate_valid_until else None,
        "mobilizationLeadTime": offer.mobilization_lead_time,
        "workLocation": offer.work_location,
        "lastVerifiedAt": offer.last_verified_at.isoformat() if offer.last_verified_at else None,
        "verifiedById": str(offer.verified_by_id) if offer.verified_by_id else None,
        "verificationNote": offer.verification_note,
        "notes": offer.notes,
        "isActive": offer.is_active,
    }


def _audit_trade(*, trade, actor_membership, action: str, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=trade.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingTrade",
        object_id=trade.pk,
        object_label=f"{trade.code} · {trade.name}",
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


def _audit_offer(*, offer, actor_membership, action: str, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=offer.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingWorkforceOffer",
        object_id=offer.pk,
        object_label=f"{offer.supplier.name} · {offer.trade.name}",
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


def _record_revision(*, offer, actor_membership, before, after, contact_name: str, note: str):
    return SourcingWorkforceOfferRevision.objects.create(
        company=offer.company,
        offer=offer,
        offer_id_snapshot=offer.pk,
        supplier_id_snapshot=offer.supplier_id,
        trade_id_snapshot=offer.trade_id,
        before=before or {},
        after=after or {},
        verified_at=timezone.now(),
        actor=actor_membership.user,
        contact_name=str(contact_name or "").strip()[:160],
        note=str(note or "").strip()[:500],
    )


def _usable_supplier(*, company, supplier_id) -> SourcingManpowerSupplier:
    supplier = (
        SourcingManpowerSupplier.objects.select_for_update()
        .for_company(company)
        .get(pk=supplier_id, deleted_at__isnull=True)
    )
    if supplier.archived_at:
        raise ValidationError("Restore the archived Manpower Supplier before changing its Workforce Catalog.")
    return supplier


@transaction.atomic
def create_trade(*, actor_membership, cleaned_data: dict[str, object], request=None) -> SourcingTrade:
    data = dict(cleaned_data)
    if not str(data.get("code") or "").strip():
        data["code"] = suggest_trade_code()
    trade = SourcingTrade(company=actor_membership.company, **data)
    trade.save()
    _audit_trade(
        trade=trade,
        actor_membership=actor_membership,
        action="sourcing.trade.created",
        after=_trade_snapshot(trade),
        request=request,
    )
    return trade


@transaction.atomic
def update_trade(*, actor_membership, trade_id, cleaned_data: dict[str, object], request=None) -> SourcingTrade:
    trade = SourcingTrade.objects.select_for_update().for_company(actor_membership.company).get(pk=trade_id)
    before = _trade_snapshot(trade)
    for field, value in cleaned_data.items():
        setattr(trade, field, value)
    trade.save()
    _audit_trade(
        trade=trade,
        actor_membership=actor_membership,
        action="sourcing.trade.updated",
        before=before,
        after=_trade_snapshot(trade),
        request=request,
    )
    return trade


@transaction.atomic
def set_trade_active(*, actor_membership, trade_id, is_active: bool, request=None) -> SourcingTrade:
    trade = SourcingTrade.objects.select_for_update().for_company(actor_membership.company).get(pk=trade_id)
    before = _trade_snapshot(trade)
    trade.is_active = bool(is_active)
    trade.save(update_fields=["is_active", "updated_at"])
    _audit_trade(
        trade=trade,
        actor_membership=actor_membership,
        action="sourcing.trade.activated" if trade.is_active else "sourcing.trade.deactivated",
        before=before,
        after=_trade_snapshot(trade),
        request=request,
    )
    return trade




@transaction.atomic
def delete_trade(*, actor_membership, trade_id, confirmation: str, request=None) -> dict[str, object]:
    """Permanently remove a Sourcing Trade and every Sourcing workforce row using it."""
    trade = SourcingTrade.objects.select_for_update().for_company(actor_membership.company).get(pk=trade_id)
    expected = trade.code
    if str(confirmation or "").strip().casefold() != expected.casefold():
        raise ValidationError({"confirmation": f"Type {expected} to confirm permanent deletion."})
    before = _trade_snapshot(trade)
    offer_ids = list(
        SourcingWorkforceOffer.objects.select_for_update()
        .for_company(trade.company)
        .filter(trade=trade)
        .values_list("pk", flat=True)
    )
    revision_count = 0
    if offer_ids:
        revisions = SourcingWorkforceOfferRevision._base_manager.filter(
            company_id=trade.company_id, offer_id__in=offer_ids
        )
        revision_count = revisions.count()
        revisions.update(offer=None)
    label = trade.name
    _audit_trade(
        trade=trade,
        actor_membership=actor_membership,
        action="sourcing.trade.deleted",
        before=before,
        after=None,
        metadata={
            "permanent": True,
            "cascadeWorkforceOffers": len(offer_ids),
            "retainedVerificationRevisions": revision_count,
        },
        request=request,
    )
    if offer_ids:
        SourcingWorkforceOffer.objects.for_company(trade.company).filter(pk__in=offer_ids).delete()
    trade.delete()
    return {"label": label, "code": expected, "offers_deleted": len(offer_ids), "revisions_retained": revision_count}


@transaction.atomic
def create_workforce_offer(
    *, actor_membership, supplier_id, cleaned_data: dict[str, object], verified_now: bool, contact_name: str = "", request=None
) -> SourcingWorkforceOffer:
    supplier = _usable_supplier(company=actor_membership.company, supplier_id=supplier_id)
    data = dict(cleaned_data)
    trade = data.get("trade")
    if not isinstance(trade, SourcingTrade) or trade.company_id != supplier.company_id:
        raise ValidationError({"trade": "Choose a Sourcing Trade from this company."})
    if not trade.is_active:
        raise ValidationError({"trade": "Inactive Sourcing Trades cannot be added to a new Workforce Catalog row."})

    offer = SourcingWorkforceOffer(company=supplier.company, supplier=supplier, **data)
    if verified_now:
        offer.last_verified_at = timezone.now()
        offer.verified_by = actor_membership.user
    offer.save()
    after = _offer_snapshot(offer)
    _record_revision(
        offer=offer,
        actor_membership=actor_membership,
        before={},
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )
    if verified_now:
        supplier.last_verified_at = offer.last_verified_at
        supplier.save(update_fields=["last_verified_at", "updated_at"])
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.workforce_offer.created",
        after=after,
        metadata={"verifiedNow": bool(verified_now), "contactName": str(contact_name or "").strip()[:160]},
        request=request,
    )
    return offer


@transaction.atomic
def update_workforce_offer(
    *, actor_membership, supplier_id, offer_id, cleaned_data: dict[str, object], verified_now: bool, contact_name: str = "", request=None
) -> SourcingWorkforceOffer:
    supplier = _usable_supplier(company=actor_membership.company, supplier_id=supplier_id)
    offer = (
        SourcingWorkforceOffer.objects.select_for_update()
        .select_related("trade", "supplier")
        .for_company(supplier.company)
        .get(pk=offer_id, supplier=supplier)
    )
    before = _offer_snapshot(offer)
    data = dict(cleaned_data)
    trade = data.get("trade")
    if not isinstance(trade, SourcingTrade) or trade.company_id != supplier.company_id:
        raise ValidationError({"trade": "Choose a Sourcing Trade from this company."})
    if trade.pk != offer.trade_id and not trade.is_active:
        raise ValidationError({"trade": "Inactive Sourcing Trades cannot be assigned to a Workforce Catalog row."})
    for field, value in data.items():
        setattr(offer, field, value)
    if verified_now:
        offer.last_verified_at = timezone.now()
        offer.verified_by = actor_membership.user
    offer.save()
    after = _offer_snapshot(offer)
    _record_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )
    if verified_now:
        supplier.last_verified_at = offer.last_verified_at
        supplier.save(update_fields=["last_verified_at", "updated_at"])
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.workforce_offer.updated",
        before=before,
        after=after,
        metadata={"verifiedNow": bool(verified_now), "contactName": str(contact_name or "").strip()[:160]},
        request=request,
    )
    return offer


@transaction.atomic
def set_workforce_offer_active(*, actor_membership, supplier_id, offer_id, is_active: bool, request=None) -> SourcingWorkforceOffer:
    supplier = _usable_supplier(company=actor_membership.company, supplier_id=supplier_id)
    offer = (
        SourcingWorkforceOffer.objects.select_for_update()
        .select_related("trade", "supplier")
        .for_company(supplier.company)
        .get(pk=offer_id, supplier=supplier)
    )
    before = _offer_snapshot(offer)
    offer.is_active = bool(is_active)
    offer.save(update_fields=["is_active", "updated_at"])
    after = _offer_snapshot(offer)
    _record_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name="",
        note="Workforce capability reactivated" if offer.is_active else "Workforce capability deactivated",
    )
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.workforce_offer.activated" if offer.is_active else "sourcing.workforce_offer.deactivated",
        before=before,
        after=after,
        request=request,
    )
    return offer




@transaction.atomic
def delete_workforce_offer(*, actor_membership, supplier_id, offer_id, request=None) -> dict[str, object]:
    """Permanently remove one Workforce Catalog row while retaining immutable history."""
    supplier = _usable_supplier(company=actor_membership.company, supplier_id=supplier_id)
    offer = (
        SourcingWorkforceOffer.objects.select_for_update()
        .select_related("trade", "supplier")
        .for_company(supplier.company)
        .get(pk=offer_id, supplier=supplier)
    )
    before = _offer_snapshot(offer)
    label = offer.trade.name
    revision_count = SourcingWorkforceOfferRevision._base_manager.filter(
        company_id=supplier.company_id, offer_id=offer.pk
    ).count()
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.workforce_offer.deleted",
        before=before,
        after=None,
        metadata={"permanent": True, "retainedVerificationRevisions": revision_count},
        request=request,
    )
    if revision_count:
        SourcingWorkforceOfferRevision._base_manager.filter(
            company_id=supplier.company_id, offer_id=offer.pk
        ).update(offer=None)
    offer.delete()
    return {"label": label, "revisions_retained": revision_count}


@transaction.atomic
def verify_workforce_offer(
    *,
    actor_membership,
    supplier_id,
    offer_id,
    cleaned_data: dict[str, object],
    contact_name: str = "",
    request=None,
) -> SourcingWorkforceOffer:
    """Confirm a supplier workforce reference without editing its trade identity.

    The write is restricted to Sourcing-owned availability/rate fields, stamps the
    current verifier, and appends immutable history. It never creates Rental
    workers, assignments, timesheets, payroll rates, settlements, Inventory or
    Accounting records.
    """
    supplier = _usable_supplier(company=actor_membership.company, supplier_id=supplier_id)
    offer = (
        SourcingWorkforceOffer.objects.select_for_update()
        .select_related("trade", "supplier")
        .for_company(supplier.company)
        .get(pk=offer_id, supplier=supplier)
    )
    if not offer.is_active:
        raise ValidationError("Reactivate this Workforce capability before verifying it.")

    allowed_fields = {
        "availability",
        "available_quantity",
        "rate",
        "currency",
        "rate_basis",
        "overtime_rate",
        "rate_valid_until",
        "mobilization_lead_time",
        "work_location",
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
    _record_revision(
        offer=offer,
        actor_membership=actor_membership,
        before=before,
        after=after,
        contact_name=contact_name,
        note=offer.verification_note,
    )
    supplier.last_verified_at = verified_at
    supplier.save(update_fields=["last_verified_at", "updated_at"])
    _audit_offer(
        offer=offer,
        actor_membership=actor_membership,
        action="sourcing.workforce_offer.verified",
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
