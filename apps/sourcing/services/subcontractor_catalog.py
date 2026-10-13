"""Transactional reference-only Subcontractor Service Catalog.

No Inventory, project, purchase order, manpower, or accounting relationships.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from ..models import (
    SourcingService, SourcingSubcontractor, SourcingSubcontractorService,
    SourcingSubcontractorServiceRevision,
)


def _snapshot(offer):
    """JSON-safe, deterministic reference state for auditing and verification."""
    return {
        "offerId": str(offer.pk),
        "subcontractorId": str(offer.subcontractor_id),
        "serviceId": str(offer.service_id),
        "serviceCode": offer.service.code,
        "serviceName": offer.service.name,
        "scope": offer.scope_description,
        "location": offer.service_location,
        "availability": offer.availability,
        "rate": format(Decimal(offer.rate), ".4f") if offer.rate is not None else None,
        "currency": offer.currency,
        "rateBasis": offer.rate_basis,
        "rateValidUntil": offer.rate_valid_until.isoformat() if offer.rate_valid_until else None,
        "leadTime": offer.lead_time,
        "lastVerifiedAt": offer.last_verified_at.isoformat() if offer.last_verified_at else None,
        "verifiedById": str(offer.verified_by_id) if offer.verified_by_id else None,
        "verificationNote": offer.verification_note,
        "notes": offer.notes,
        "isActive": offer.is_active,
    }


def _audit(*, offer, actor_membership, action, before=None, after=None, request=None, metadata=None):
    return record_audit_event(
        company=offer.company, area=AuditArea.SOURCING,
        action=action, object_type="sourcing.SourcingSubcontractorService",
        object_id=offer.pk,
        object_label=f"{offer.subcontractor.display_name or offer.subcontractor.name} · {offer.service.name}",
        actor_membership=actor_membership,
        before=before, after=after, request=request,
        metadata={"subcontractorId": str(offer.subcontractor_id), **(metadata or {})},
    )


def _writable_subcontractor(actor_membership, subcontractor_id):
    subcontractor = SourcingSubcontractor.objects.select_for_update().for_company(
        actor_membership.company
    ).get(pk=subcontractor_id, deleted_at__isnull=True)
    if subcontractor.archived_at:
        raise ValidationError("Restore the archived subcontractor before changing its Service Catalog.")
    return subcontractor


def _offer(subcontractor, offer_id):
    return (SourcingSubcontractorService.objects.select_for_update()
            .for_company(subcontractor.company).select_related("service", "subcontractor")
            .get(pk=offer_id, subcontractor=subcontractor))


def _validate_service(data, company, *, existing=None):
    service = data.get("service")
    if not isinstance(service, SourcingService) or service.company_id != company.pk:
        raise ValidationError({"service": "Select a Service belonging to this company."})
    if not service.is_active and (existing is None or existing.service_id != service.pk):
        raise ValidationError({"service": "Inactive Services cannot be assigned to new catalog entries."})


def _revision(*, offer, actor_membership, before, after, contact_name=""):
    return SourcingSubcontractorServiceRevision.objects.create(
        company=offer.company, offer=offer,
        offer_id_snapshot=offer.pk,
        subcontractor_id_snapshot=offer.subcontractor_id,
        service_id_snapshot=offer.service_id,
        before=before, after=after, verified_at=timezone.now(),
        actor=actor_membership.user,
        contact_name=str(contact_name or "").strip()[:160],
        note=offer.verification_note,
    )


def _mark_verified(offer, actor_membership):
    offer.last_verified_at = timezone.now()
    offer.verified_by = actor_membership.user


@transaction.atomic
def create_service_offer(*, actor_membership, subcontractor_id, cleaned_data, verified_now=False,
                         contact_name="", request=None):
    subcontractor = _writable_subcontractor(actor_membership, subcontractor_id)
    data = dict(cleaned_data)
    _validate_service(data, subcontractor.company)
    offer = SourcingSubcontractorService(company=subcontractor.company, subcontractor=subcontractor, **data)
    if verified_now:
        _mark_verified(offer, actor_membership)
    offer.save()
    after = _snapshot(offer)
    if verified_now:
        _revision(offer=offer, actor_membership=actor_membership, before={}, after=after, contact_name=contact_name)
    _audit(offer=offer, actor_membership=actor_membership, action="sourcing.subcontractor_service.created",
           after=after, metadata={"verifiedNow": bool(verified_now)}, request=request)
    return offer


@transaction.atomic
def update_service_offer(*, actor_membership, subcontractor_id, offer_id, cleaned_data,
                         verified_now=False, contact_name="", request=None):
    subcontractor = _writable_subcontractor(actor_membership, subcontractor_id)
    offer = _offer(subcontractor, offer_id)
    data = dict(cleaned_data)
    _validate_service(data, subcontractor.company, existing=offer)
    before = _snapshot(offer)
    for field, value in data.items():
        setattr(offer, field, value)
    # A changed unverified reference is NOT silently represented as fresh.
    # Comparison uses a fresh JSON snapshot after model validation (which normalizes text).
    if verified_now:
        _mark_verified(offer, actor_membership)
    offer.save()
    after = _snapshot(offer)
    reference_fields = ("serviceId", "scope", "location", "availability", "rate", "currency",
                        "rateBasis", "rateValidUntil", "leadTime")
    if not verified_now and any(before[k] != after[k] for k in reference_fields):
        offer.last_verified_at = None
        offer.verified_by = None
        offer.save(update_fields=["last_verified_at", "verified_by", "updated_at"])
        after = _snapshot(offer)
    if verified_now:
        _revision(offer=offer, actor_membership=actor_membership, before=before, after=after, contact_name=contact_name)
    _audit(offer=offer, actor_membership=actor_membership, action="sourcing.subcontractor_service.updated",
           before=before, after=after, metadata={"verifiedNow": bool(verified_now)}, request=request)
    return offer


@transaction.atomic
def verify_service_offer(*, actor_membership, subcontractor_id, offer_id, cleaned_data,
                         contact_name="", request=None):
    subcontractor = _writable_subcontractor(actor_membership, subcontractor_id)
    offer = _offer(subcontractor, offer_id)
    if not offer.is_active:
        raise ValidationError("Reactivate this service entry before verifying it.")
    if not offer.service.is_active:
        raise ValidationError("Reactivate the controlled Service before verifying its catalog references.")
    before = _snapshot(offer)
    allowed = {"availability", "rate", "currency", "rate_basis", "rate_valid_until", "lead_time", "verification_note"}
    for key, value in cleaned_data.items():
        if key in allowed:
            setattr(offer, key, value)
    _mark_verified(offer, actor_membership)
    offer.save()
    after = _snapshot(offer)
    _revision(offer=offer, actor_membership=actor_membership, before=before, after=after, contact_name=contact_name)
    _audit(offer=offer, actor_membership=actor_membership, action="sourcing.subcontractor_service.verified",
           before=before, after=after, metadata={"contactName": str(contact_name or "").strip()[:160]}, request=request)
    return offer


@transaction.atomic
def set_service_offer_active(*, actor_membership, subcontractor_id, offer_id, is_active, request=None):
    subcontractor = _writable_subcontractor(actor_membership, subcontractor_id)
    offer = _offer(subcontractor, offer_id)
    if bool(is_active) and not offer.service.is_active:
        raise ValidationError("Reactivate the controlled Service before enabling this catalog reference.")
    before = _snapshot(offer)
    offer.is_active = bool(is_active)
    offer.save(update_fields=["is_active", "updated_at"])
    _audit(offer=offer, actor_membership=actor_membership,
           action="sourcing.subcontractor_service.activated" if offer.is_active else "sourcing.subcontractor_service.deactivated",
           before=before, after=_snapshot(offer), request=request)
    return offer


@transaction.atomic
def delete_service_offer(*, actor_membership, subcontractor_id, offer_id, confirmation, request=None):
    subcontractor = _writable_subcontractor(actor_membership, subcontractor_id)
    offer = _offer(subcontractor, offer_id)
    if str(confirmation or "").strip().casefold() != offer.service.code.casefold():
        raise ValidationError({"confirmation": f"Type {offer.service.code} to confirm permanent removal."})
    before = _snapshot(offer)
    revision_count = SourcingSubcontractorServiceRevision._base_manager.filter(
        company_id=subcontractor.company_id, offer_id=offer.pk).count()
    _audit(offer=offer, actor_membership=actor_membership, action="sourcing.subcontractor_service.deleted",
           before=before, metadata={"permanent": True, "revisionsRetained": revision_count}, request=request)
    # The FK SET_NULL preserves immutable snapshot rows after removing the live offer.
    if revision_count:
        SourcingSubcontractorServiceRevision._base_manager.filter(
            company_id=subcontractor.company_id, offer_id=offer.pk).update(offer=None)
    offer.delete()
    return {"label": before["serviceName"], "revisions_retained": revision_count}
