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
    SourcingManpowerContact,
    SourcingManpowerSupplier,
    SourcingWorkforceOffer,
    SourcingWorkforceOfferRevision,
)

TRASH_RETENTION_DAYS = 30


def suggest_manpower_supplier_code() -> str:
    return f"MPS-{uuid4().hex[:8].upper()}"


def _supplier_snapshot(supplier: SourcingManpowerSupplier) -> dict[str, object]:
    return {
        "code": supplier.code,
        "name": supplier.name,
        "primaryContactName": supplier.primary_contact_name,
        "phone": supplier.phone,
        "mobile": supplier.mobile,
        "email": supplier.email,
        "city": supplier.city,
        "region": supplier.region,
        "crNumber": supplier.cr_number,
        "vatNumber": supplier.vat_number,
        "status": supplier.status,
        "archivedAt": supplier.archived_at.isoformat() if supplier.archived_at else None,
        "deletedAt": supplier.deleted_at.isoformat() if supplier.deleted_at else None,
        "purgeAfter": supplier.purge_after.isoformat() if supplier.purge_after else None,
    }


def _contact_snapshot(contact: SourcingManpowerContact) -> dict[str, object]:
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


def _sync_primary_contact_summary(supplier: SourcingManpowerSupplier, contact: SourcingManpowerContact) -> None:
    if not contact.is_primary or not contact.is_active:
        return
    supplier.primary_contact_name = contact.full_name
    if contact.email and not supplier.email:
        supplier.email = contact.email
    if contact.work_phone and not supplier.phone:
        supplier.phone = contact.work_phone
    if contact.mobile and not supplier.mobile:
        supplier.mobile = contact.mobile
    supplier.save(update_fields=["primary_contact_name", "email", "phone", "mobile", "updated_at"])


def _audit(*, supplier, actor_membership, action: str, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=supplier.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingManpowerSupplier",
        object_id=supplier.pk,
        object_label=supplier.name,
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


@transaction.atomic
def create_manpower_supplier(*, actor_membership, cleaned_data: dict[str, object], request=None) -> SourcingManpowerSupplier:
    data = dict(cleaned_data)
    if not str(data.get("code") or "").strip():
        data["code"] = suggest_manpower_supplier_code()
    supplier = SourcingManpowerSupplier(company=actor_membership.company, **data)
    supplier.save()
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.created", after=_supplier_snapshot(supplier), request=request)
    return supplier


@transaction.atomic
def update_manpower_supplier(*, actor_membership, supplier_id, cleaned_data: dict[str, object], request=None) -> SourcingManpowerSupplier:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    before = _supplier_snapshot(supplier)
    for field, value in cleaned_data.items():
        setattr(supplier, field, value)
    supplier.save()
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.updated", before=before, after=_supplier_snapshot(supplier), request=request)
    return supplier


@transaction.atomic
def set_manpower_supplier_status(*, actor_membership, supplier_id, status: str, request=None) -> SourcingManpowerSupplier:
    if status not in {SourcingEntityStatus.ACTIVE, SourcingEntityStatus.INACTIVE}:
        raise ValidationError({"status": "Choose Active or Inactive."})
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    if supplier.archived_at:
        raise ValidationError("Restore the archived Manpower Supplier before changing its status.")
    before = _supplier_snapshot(supplier)
    supplier.status = status
    supplier.save(update_fields=["status", "updated_at"])
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.status_changed", before=before, after=_supplier_snapshot(supplier), request=request)
    return supplier


@transaction.atomic
def archive_manpower_supplier(*, actor_membership, supplier_id, reason: str, request=None) -> SourcingManpowerSupplier:
    reason = str(reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required to archive a Manpower Supplier."})
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    before = _supplier_snapshot(supplier)
    changed_fields = []
    if not supplier.archived_at:
        supplier.archived_at = timezone.now()
        supplier.archived_reason = reason[:300]
        changed_fields.extend(["archived_at", "archived_reason"])
    if supplier.status != SourcingEntityStatus.INACTIVE:
        supplier.status = SourcingEntityStatus.INACTIVE
        changed_fields.append("status")
    if changed_fields:
        supplier.save(update_fields=[*changed_fields, "updated_at"])
        _audit(
            supplier=supplier,
            actor_membership=actor_membership,
            action="sourcing.manpower_supplier.archived",
            before=before,
            after=_supplier_snapshot(supplier),
            metadata={"reason": reason[:300], "statusForcedInactive": True},
            request=request,
        )
    return supplier


@transaction.atomic
def restore_manpower_supplier_archive(*, actor_membership, supplier_id, request=None) -> SourcingManpowerSupplier:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    before = _supplier_snapshot(supplier)
    supplier.archived_at = None
    supplier.archived_reason = ""
    supplier.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.archive_restored", before=before, after=_supplier_snapshot(supplier), request=request)
    return supplier


@transaction.atomic
def trash_manpower_supplier(*, actor_membership, supplier_id, confirmation: str, reason: str, request=None) -> SourcingManpowerSupplier:
    reason = str(reason or "").strip()
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    if not reason:
        raise ValidationError({"reason": "A reason is required to move a Manpower Supplier to Trash."})
    expected = supplier.code
    if str(confirmation or "").strip().casefold() != expected.casefold():
        raise ValidationError({"confirmation": f"Type {expected} to confirm deletion."})
    before = _supplier_snapshot(supplier)
    now = timezone.now()
    supplier.deleted_at = now
    supplier.purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)
    supplier.deletion_reason = reason[:500]
    supplier.deleted_by = actor_membership.user
    supplier.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.trashed", before=before, after=_supplier_snapshot(supplier), metadata={"retentionDays": TRASH_RETENTION_DAYS, "reason": reason[:500]}, request=request)
    return supplier


@transaction.atomic
def restore_manpower_supplier_trash(*, actor_membership, supplier_id, request=None) -> SourcingManpowerSupplier:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=False)
    before = _supplier_snapshot(supplier)
    supplier.deleted_at = None
    supplier.purge_after = None
    supplier.deletion_reason = ""
    supplier.deleted_by = None
    supplier.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.trash_restored", before=before, after=_supplier_snapshot(supplier), request=request)
    return supplier




@transaction.atomic
def delete_manpower_supplier(*, actor_membership, supplier_id, confirmation: str, reason: str, request=None) -> dict[str, object]:
    """Permanently delete one Sourcing Manpower Supplier and Sourcing children only.

    Workforce capability rows and contacts are removed immediately. Immutable
    verification snapshots remain detached for audit evidence; Rental Payroll suppliers,
    workers, assignments, settlements and Accounting are intentionally untouched.
    """
    reason = str(reason or "").strip()
    supplier = (
        SourcingManpowerSupplier.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=supplier_id)
    )
    expected = supplier.code
    if str(confirmation or "").strip().casefold() != expected.casefold():
        raise ValidationError({"confirmation": f"Type {expected} to confirm permanent deletion."})
    if not reason:
        raise ValidationError({"reason": "A reason is required to permanently delete a Manpower Supplier."})

    before = _supplier_snapshot(supplier)
    offer_ids = list(
        SourcingWorkforceOffer.objects.select_for_update()
        .for_company(supplier.company)
        .filter(supplier=supplier)
        .values_list("pk", flat=True)
    )
    contact_count = SourcingManpowerContact.objects.for_company(supplier.company).filter(supplier=supplier).count()
    revision_count = 0
    if offer_ids:
        revisions = SourcingWorkforceOfferRevision._base_manager.filter(
            company_id=supplier.company_id, offer_id__in=offer_ids
        )
        revision_count = revisions.count()
        revisions.update(offer=None)

    label = supplier.name
    _audit(
        supplier=supplier,
        actor_membership=actor_membership,
        action="sourcing.manpower_supplier.deleted",
        before=before,
        after=None,
        metadata={
            "reason": reason[:500],
            "permanent": True,
            "cascadeContacts": contact_count,
            "cascadeWorkforceOffers": len(offer_ids),
            "retainedVerificationRevisions": revision_count,
        },
        request=request,
    )
    if offer_ids:
        SourcingWorkforceOffer.objects.for_company(supplier.company).filter(pk__in=offer_ids).delete()
    SourcingManpowerContact.objects.for_company(supplier.company).filter(supplier=supplier).delete()
    supplier.delete()
    return {
        "label": label,
        "code": expected,
        "contacts_deleted": contact_count,
        "offers_deleted": len(offer_ids),
        "revisions_retained": revision_count,
    }


@transaction.atomic
def create_manpower_contact(*, actor_membership, supplier_id, cleaned_data: dict[str, object], request=None) -> SourcingManpowerContact:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    data = dict(cleaned_data)
    if data.get("is_primary"):
        SourcingManpowerContact.objects.for_company(supplier.company).filter(supplier=supplier, is_primary=True).update(is_primary=False)
    contact = SourcingManpowerContact(company=supplier.company, supplier=supplier, **data)
    contact.save()
    _sync_primary_contact_summary(supplier, contact)
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.contact_created", after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def update_manpower_contact(*, actor_membership, supplier_id, contact_id, cleaned_data: dict[str, object], request=None) -> SourcingManpowerContact:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    contact = SourcingManpowerContact.objects.select_for_update().for_company(supplier.company).get(pk=contact_id, supplier=supplier)
    before = _contact_snapshot(contact)
    data = dict(cleaned_data)
    if data.get("is_primary"):
        SourcingManpowerContact.objects.for_company(supplier.company).filter(supplier=supplier, is_primary=True).exclude(pk=contact.pk).update(is_primary=False)
    for field, value in data.items():
        setattr(contact, field, value)
    contact.is_active = True
    contact.save()
    _sync_primary_contact_summary(supplier, contact)
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.contact_updated", before=before, after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def deactivate_manpower_contact(*, actor_membership, supplier_id, contact_id, request=None) -> SourcingManpowerContact:
    supplier = SourcingManpowerSupplier.objects.select_for_update().for_company(actor_membership.company).get(pk=supplier_id, deleted_at__isnull=True)
    contact = SourcingManpowerContact.objects.select_for_update().for_company(supplier.company).get(pk=contact_id, supplier=supplier)
    before = _contact_snapshot(contact)
    contact.is_active = False
    contact.is_primary = False
    contact.save(update_fields=["is_active", "is_primary", "updated_at"])
    _audit(supplier=supplier, actor_membership=actor_membership, action="sourcing.manpower_supplier.contact_deactivated", before=before, after=_contact_snapshot(contact), metadata={"contactId": str(contact.pk)}, request=request)
    return contact


@transaction.atomic
def delete_manpower_contact(*, actor_membership, supplier_id, contact_id, request=None) -> dict[str, str]:
    """Permanently delete one Manpower Supplier contact; deactivation remains reversible."""
    supplier = (
        SourcingManpowerSupplier.objects.select_for_update()
        .for_company(actor_membership.company)
        .get(pk=supplier_id, deleted_at__isnull=True)
    )
    if supplier.archived_at:
        raise ValidationError("Restore the archived Manpower Supplier before deleting a contact.")
    contact = (
        SourcingManpowerContact.objects.select_for_update()
        .for_company(supplier.company)
        .get(pk=contact_id, supplier=supplier)
    )
    before = _contact_snapshot(contact)
    contact_id_text = str(contact.pk)
    label = contact.full_name
    _audit(
        supplier=supplier,
        actor_membership=actor_membership,
        action="sourcing.manpower_supplier.contact_deleted",
        before=before,
        after=None,
        metadata={"contactId": contact_id_text, "permanent": True},
        request=request,
    )
    contact.delete()
    return {"label": label, "contact_id": contact_id_text}
