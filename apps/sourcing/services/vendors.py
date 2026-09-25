from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from ..models import (
    SourcingEntityStatus,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
    SourcingVendorOfferRevision,
)

TRASH_RETENTION_DAYS = 30


def suggest_vendor_code() -> str:
    return f"VND-{uuid4().hex[:8].upper()}"


def _vendor_snapshot(vendor: SourcingVendor) -> dict[str, object]:
    return {
        "code": vendor.code,
        "name": vendor.name,
        "displayName": vendor.display_name,
        "primaryContactName": vendor.primary_contact_name,
        "companyPhone": vendor.company_phone,
        "companyEmail": vendor.company_email,
        "mobile": vendor.mobile,
        "email": vendor.email,
        "address": vendor.address,
        "streetNumber": vendor.street_number,
        "district": vendor.district,
        "city": vendor.city,
        "region": vendor.region,
        "postalCode": vendor.postal_code,
        "crNumber": vendor.cr_number,
        "vatNumber": vendor.vat_number,
        "website": vendor.website,
        "status": vendor.status,
        "archivedAt": vendor.archived_at.isoformat() if vendor.archived_at else None,
        "deletedAt": vendor.deleted_at.isoformat() if vendor.deleted_at else None,
        "purgeAfter": vendor.purge_after.isoformat() if vendor.purge_after else None,
    }


def _contact_snapshot(contact: SourcingVendorContact) -> dict[str, object]:
    return {
        "contactId": str(contact.pk),
        "name": contact.full_name,
        "salutation": contact.salutation,
        "designation": contact.designation,
        "department": contact.department,
        "email": contact.email,
        "workPhone": contact.work_phone,
        "mobile": contact.mobile,
        "isPrimary": contact.is_primary,
        "isActive": contact.is_active,
    }



def _sync_primary_contact_summary(vendor: SourcingVendor, contact: SourcingVendorContact) -> None:
    """Keep the fast Vendor list summary aligned with an explicitly primary contact."""
    if not contact.is_primary or not contact.is_active:
        return
    vendor.primary_contact_name = contact.full_name
    if contact.email:
        vendor.email = contact.email
    if contact.mobile:
        vendor.mobile = contact.mobile
    vendor.save(update_fields=["primary_contact_name", "email", "mobile", "updated_at"])

def _audit(*, vendor, actor_membership, action: str, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=vendor.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingVendor",
        object_id=vendor.pk,
        object_label=vendor.display_name or vendor.name,
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


@transaction.atomic
def create_vendor(*, actor_membership, cleaned_data: dict[str, object], request=None) -> SourcingVendor:
    data = dict(cleaned_data)
    if not str(data.get("code") or "").strip():
        data["code"] = suggest_vendor_code()
    vendor = SourcingVendor(company=actor_membership.company, **data)
    vendor.save()
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.created", after=_vendor_snapshot(vendor), request=request)
    return vendor


@transaction.atomic
def update_vendor(*, actor_membership, vendor_id, cleaned_data: dict[str, object], request=None) -> SourcingVendor:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    before = _vendor_snapshot(vendor)
    for field, value in cleaned_data.items():
        setattr(vendor, field, value)
    vendor.save()
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.updated", before=before, after=_vendor_snapshot(vendor), request=request)
    return vendor


@transaction.atomic
def set_vendor_status(*, actor_membership, vendor_id, status: str, request=None) -> SourcingVendor:
    if status not in {SourcingEntityStatus.ACTIVE, SourcingEntityStatus.INACTIVE}:
        raise ValidationError({"status": "Choose Active or Inactive."})
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    if vendor.archived_at:
        raise ValidationError("Restore the archived Vendor before changing its status.")
    before = _vendor_snapshot(vendor)
    vendor.status = status
    vendor.save(update_fields=["status", "updated_at"])
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.status_changed", before=before, after=_vendor_snapshot(vendor), request=request)
    return vendor


@transaction.atomic
def archive_vendor(*, actor_membership, vendor_id, reason: str, request=None) -> SourcingVendor:
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required to archive a Vendor."})
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    before = _vendor_snapshot(vendor)
    changed_fields = []
    if not vendor.archived_at:
        vendor.archived_at = timezone.now()
        vendor.archived_reason = reason[:300]
        changed_fields.extend(["archived_at", "archived_reason"])
    if vendor.status != SourcingEntityStatus.INACTIVE:
        vendor.status = SourcingEntityStatus.INACTIVE
        changed_fields.append("status")
    if changed_fields:
        vendor.save(update_fields=[*changed_fields, "updated_at"])
        _audit(
            vendor=vendor,
            actor_membership=actor_membership,
            action="sourcing.vendor.archived",
            before=before,
            after=_vendor_snapshot(vendor),
            metadata={"reason": reason[:300], "statusForcedInactive": True},
            request=request,
        )
    return vendor


@transaction.atomic
def restore_vendor_archive(*, actor_membership, vendor_id, request=None) -> SourcingVendor:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    before = _vendor_snapshot(vendor)
    vendor.archived_at = None
    vendor.archived_reason = ""
    vendor.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.archive_restored", before=before, after=_vendor_snapshot(vendor), request=request)
    return vendor


@transaction.atomic
def trash_vendor(*, actor_membership, vendor_id, confirmation: str, reason: str, request=None) -> SourcingVendor:
    reason = str(reason or "").strip()
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    if not reason:
        raise ValidationError({"reason": "A reason is required to move a Vendor to Trash."})
    expected = vendor.code
    if str(confirmation or "").strip().casefold() != expected.casefold():
        raise ValidationError({"confirmation": f"Type {expected} to confirm deletion."})
    before = _vendor_snapshot(vendor)
    now = timezone.now()
    vendor.deleted_at = now
    vendor.purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)
    vendor.deletion_reason = reason[:500]
    vendor.deleted_by = actor_membership.user
    vendor.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.trashed", before=before, after=_vendor_snapshot(vendor), metadata={"retentionDays": TRASH_RETENTION_DAYS, "reason": reason[:500]}, request=request)
    return vendor


@transaction.atomic
def restore_vendor_trash(*, actor_membership, vendor_id, request=None) -> SourcingVendor:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=False)
    before = _vendor_snapshot(vendor)
    vendor.deleted_at = None
    vendor.purge_after = None
    vendor.deletion_reason = ""
    vendor.deleted_by = None
    vendor.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.trash_restored", before=before, after=_vendor_snapshot(vendor), request=request)
    return vendor




@transaction.atomic
def delete_vendor(*, actor_membership, vendor_id, confirmation: str, reason: str, request=None) -> dict[str, object]:
    """Permanently delete one Sourcing Vendor and its Sourcing-owned children.

    Archive and Inactive remain reversible lifecycle states. Permanent deletion removes
    the live Vendor row, contacts, and Supply Catalog rows immediately. Immutable
    verification snapshots are intentionally retained with their offer FK detached, and
    operational Inventory/Payroll/Accounting records are never touched.
    """
    reason = str(reason or "").strip()
    vendor = (
        SourcingVendor.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=vendor_id)
    )
    expected = vendor.code
    if str(confirmation or "").strip().casefold() != expected.casefold():
        raise ValidationError({"confirmation": f"Type {expected} to confirm permanent deletion."})
    if not reason:
        raise ValidationError({"reason": "A reason is required to permanently delete a Vendor."})

    before = _vendor_snapshot(vendor)
    offer_ids = list(
        SourcingVendorOffer.objects.select_for_update()
        .for_company(vendor.company)
        .filter(vendor=vendor)
        .values_list("pk", flat=True)
    )
    contact_count = SourcingVendorContact.objects.for_company(vendor.company).filter(vendor=vendor).count()
    revision_count = 0
    if offer_ids:
        revisions = SourcingVendorOfferRevision._base_manager.filter(
            company_id=vendor.company_id, offer_id__in=offer_ids
        )
        revision_count = revisions.count()
        # Keep immutable verification evidence while removing the live catalog rows.
        revisions.update(offer=None)

    label = vendor.display_name or vendor.name
    _audit(
        vendor=vendor,
        actor_membership=actor_membership,
        action="sourcing.vendor.deleted",
        before=before,
        after=None,
        metadata={
            "reason": reason[:500],
            "permanent": True,
            "cascadeContacts": contact_count,
            "cascadeSupplyOffers": len(offer_ids),
            "retainedVerificationRevisions": revision_count,
        },
        request=request,
    )
    if offer_ids:
        SourcingVendorOffer.objects.for_company(vendor.company).filter(pk__in=offer_ids).delete()
    # Contacts are CASCADE children, but deleting explicitly makes the destructive scope
    # deterministic before the parent row is removed.
    SourcingVendorContact.objects.for_company(vendor.company).filter(vendor=vendor).delete()
    vendor.delete()
    return {
        "label": label,
        "code": expected,
        "contacts_deleted": contact_count,
        "offers_deleted": len(offer_ids),
        "revisions_retained": revision_count,
    }


@transaction.atomic
def create_vendor_contact(*, actor_membership, vendor_id, cleaned_data: dict[str, object], request=None) -> SourcingVendorContact:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    data = dict(cleaned_data)
    if data.get("is_primary"):
        SourcingVendorContact.objects.for_company(vendor.company).filter(vendor=vendor, is_primary=True).update(is_primary=False)
    contact = SourcingVendorContact(company=vendor.company, vendor=vendor, **data)
    contact.save()
    _sync_primary_contact_summary(vendor, contact)
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.contact_created", after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def update_vendor_contact(*, actor_membership, vendor_id, contact_id, cleaned_data: dict[str, object], request=None) -> SourcingVendorContact:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    contact = SourcingVendorContact.objects.select_for_update().for_company(vendor.company).get(pk=contact_id, vendor=vendor)
    before = _contact_snapshot(contact)
    data = dict(cleaned_data)
    if data.get("is_primary"):
        SourcingVendorContact.objects.for_company(vendor.company).filter(vendor=vendor, is_primary=True).exclude(pk=contact.pk).update(is_primary=False)
    for field, value in data.items():
        setattr(contact, field, value)
    contact.is_active = True
    contact.save()
    _sync_primary_contact_summary(vendor, contact)
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.contact_updated", before=before, after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def deactivate_vendor_contact(*, actor_membership, vendor_id, contact_id, request=None) -> SourcingVendorContact:
    vendor = SourcingVendor.objects.select_for_update().for_company(actor_membership.company).get(pk=vendor_id, deleted_at__isnull=True)
    contact = SourcingVendorContact.objects.select_for_update().for_company(vendor.company).get(pk=contact_id, vendor=vendor)
    before = _contact_snapshot(contact)
    contact.is_active = False
    contact.is_primary = False
    contact.save(update_fields=["is_active", "is_primary", "updated_at"])
    _audit(vendor=vendor, actor_membership=actor_membership, action="sourcing.vendor.contact_deactivated", before=before, after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def delete_vendor_contact(*, actor_membership, vendor_id, contact_id, request=None) -> dict[str, str]:
    """Permanently delete one Vendor contact; deactivation remains reversible."""
    vendor = (
        SourcingVendor.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=vendor_id, deleted_at__isnull=True)
    )
    if vendor.archived_at:
        raise ValidationError("Restore the archived Vendor before deleting a contact.")
    contact = (
        SourcingVendorContact.objects.select_for_update()
        .for_company(vendor.company)
        .get(pk=contact_id, vendor=vendor)
    )
    before = _contact_snapshot(contact)
    contact_id_text = str(contact.pk)
    label = contact.full_name
    _audit(
        vendor=vendor,
        actor_membership=actor_membership,
        action="sourcing.vendor.contact_deleted",
        before=before,
        after=None,
        metadata={"contactId": contact_id_text, "permanent": True},
        request=request,
    )
    contact.delete()
    return {"label": label, "contact_id": contact_id_text}
