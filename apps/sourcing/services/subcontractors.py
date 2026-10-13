"""Company-isolated, auditable subcontractor and contact lifecycle.

Reference-only: no Inventory, Projects, Payroll, PO or accounting effects.
"""
from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from ..models import (
    SourcingEntityStatus, SourcingSubcontractor, SourcingSubcontractorContact,
    SourcingSubcontractorService, SourcingSubcontractorVerificationRevision,
    SourcingSubcontractorDocument,
)

TRASH_RETENTION_DAYS = 30


def suggest_subcontractor_code():
    return f"SUB-{uuid4().hex[:8].upper()}"


def _snapshot(obj):
    keys = (
        "code", "name", "display_name", "primary_contact_name", "company_phone",
        "company_email", "mobile", "email", "address", "street_number", "district",
        "city", "region", "postal_code", "service_coverage", "cr_number", "vat_number",
        "website", "status", "tags", "notes", "archived_reason", "deletion_reason",
        "last_verified_at",
    )
    data = {field: getattr(obj, field) for field in keys}
    if data["last_verified_at"]:
        data["last_verified_at"] = data["last_verified_at"].isoformat()
    for attr in ("archived_at", "deleted_at", "purge_after"):
        value = getattr(obj, attr)
        data[attr] = value.isoformat() if value else None
    return data


def _contact_snapshot(contact):
    keys = ("salutation", "first_name", "last_name", "designation", "department", "email", "work_phone", "mobile", "is_primary", "is_active")
    return {"id": str(contact.pk), **{key: getattr(contact, key) for key in keys}}


def _audit(*, subcontractor, actor_membership, action, before=None, after=None, request=None, metadata=None):
    return record_audit_event(
        company=subcontractor.company,
        area=AuditArea.SOURCING,
        action=action,
        object_type="sourcing.SourcingSubcontractor",
        object_id=subcontractor.pk,
        object_label=subcontractor.display_name or subcontractor.name,
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata=metadata,
        request=request,
    )


def _current(actor_membership, subcontractor_id, *, include_trash=False):
    qs = SourcingSubcontractor.objects.select_for_update().for_company(actor_membership.company)
    if not include_trash:
        qs = qs.filter(deleted_at__isnull=True)
    return qs.get(pk=subcontractor_id)


def _writable(subcontractor):
    if subcontractor.archived_at or subcontractor.deleted_at:
        raise ValidationError("Restore the subcontractor before editing its profile or contacts.")


@transaction.atomic
def create_subcontractor(*, actor_membership, cleaned_data, request=None):
    data = dict(cleaned_data)
    data["code"] = data.get("code") or suggest_subcontractor_code()
    subcontractor = SourcingSubcontractor(company=actor_membership.company, **data)
    subcontractor.save()
    _audit(subcontractor=subcontractor, actor_membership=actor_membership, action="sourcing.subcontractor.created", after=_snapshot(subcontractor), request=request)
    return subcontractor


@transaction.atomic
def update_subcontractor(*, actor_membership, subcontractor_id, cleaned_data, request=None):
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    before = _snapshot(obj)
    for field, value in cleaned_data.items():
        setattr(obj, field, value)
    # A substantive company-profile change invalidates its prior confirmation.
    # Internal remarks alone do not change the reference's verified identity.
    verified_fields = ("name", "display_name", "cr_number", "vat_number", "company_phone",
                       "company_email", "primary_contact_name", "mobile", "email", "website",
                       "address", "street_number", "district", "city", "region",
                       "postal_code", "service_coverage")
    if any(before[field] != getattr(obj, field) for field in verified_fields):
        obj.last_verified_at = None
    obj.save()
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.updated", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def set_subcontractor_status(*, actor_membership, subcontractor_id, status, request=None):
    if status not in {SourcingEntityStatus.ACTIVE, SourcingEntityStatus.INACTIVE}:
        raise ValidationError({"status": "Choose Active or Inactive."})
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    before = _snapshot(obj)
    obj.status = status
    obj.save(update_fields=["status", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.status_changed", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def archive_subcontractor(*, actor_membership, subcontractor_id, reason, request=None):
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Reason is required to archive a subcontractor."})
    obj = _current(actor_membership, subcontractor_id)
    before = _snapshot(obj)
    obj.archived_at = timezone.now()
    obj.archived_reason = str(reason).strip()[:300]
    obj.status = SourcingEntityStatus.INACTIVE
    obj.save(update_fields=["archived_at", "archived_reason", "status", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.archived", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def restore_subcontractor_archive(*, actor_membership, subcontractor_id, request=None):
    obj = _current(actor_membership, subcontractor_id)
    before = _snapshot(obj)
    obj.archived_at = None
    obj.archived_reason = ""
    obj.save(update_fields=["archived_at", "archived_reason", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.archive_restored", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def trash_subcontractor(*, actor_membership, subcontractor_id, confirmation, reason, request=None):
    obj = _current(actor_membership, subcontractor_id)
    if str(confirmation or "").strip().casefold() != obj.code.casefold():
        raise ValidationError({"confirmation": f"Type {obj.code} to confirm."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "Reason is required to move a subcontractor to Trash."})
    before = _snapshot(obj)
    now = timezone.now()
    obj.deleted_at = now
    obj.purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)
    obj.deletion_reason = str(reason).strip()[:500]
    obj.deleted_by = actor_membership.user
    obj.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.trashed", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def restore_subcontractor_trash(*, actor_membership, subcontractor_id, request=None):
    obj = _current(actor_membership, subcontractor_id, include_trash=True)
    if not obj.deleted_at or (obj.purge_after and obj.purge_after <= timezone.now()):
        raise ValidationError("This record cannot be restored from Trash.")
    before = _snapshot(obj)
    obj.deleted_at = None
    obj.purge_after = None
    obj.deletion_reason = ""
    obj.deleted_by = None
    obj.save(update_fields=["deleted_at", "purge_after", "deletion_reason", "deleted_by", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.trash_restored", before=before, after=_snapshot(obj), request=request)
    return obj


@transaction.atomic
def delete_subcontractor(*, actor_membership, subcontractor_id, confirmation, reason, request=None):
    obj = _current(actor_membership, subcontractor_id, include_trash=True)
    if str(confirmation or "").strip().casefold() != obj.code.casefold():
        raise ValidationError({"confirmation": f"Type {obj.code} to confirm permanent deletion."})
    if not str(reason or "").strip():
        raise ValidationError({"reason": "A reason is required for permanent deletion."})
    # Do not cascade into protected service capabilities or immutable verification
    # evidence. Catalog removal, with revision retention, arrives in Upgrade 04.
    if SourcingSubcontractorService.objects.for_company(obj.company).filter(subcontractor=obj).exists():
        raise ValidationError("Remove service catalog entries before permanently deleting this subcontractor.")
    if SourcingSubcontractorDocument.objects.for_company(obj.company).filter(subcontractor=obj).exists():
        raise ValidationError("Remove qualification documents before permanently deleting this subcontractor.")
    before = _snapshot(obj)
    count = SourcingSubcontractorContact.objects.for_company(obj.company).filter(subcontractor=obj).count()
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.deleted", before=before, after=None, metadata={"reason": str(reason).strip()[:500], "contactsDeleted": count}, request=request)
    SourcingSubcontractorContact.objects.for_company(obj.company).filter(subcontractor=obj).delete()
    # Keep append-only company confirmations independently of the live profile.
    # Detach through the trusted base manager, as done for Service revisions.
    SourcingSubcontractorVerificationRevision._base_manager.filter(
        company_id=obj.company_id, subcontractor_id=obj.pk,
    ).update(subcontractor=None)
    obj.delete()
    return obj.code


def _sync_primary(obj, contact):
    # Preserve explicit profile contact values unless new primary details exist.
    if contact.is_active and contact.is_primary:
        obj.last_verified_at = None
        obj.primary_contact_name = contact.full_name
        if contact.email:
            obj.email = contact.email
        if contact.mobile:
            obj.mobile = contact.mobile
        obj.save(update_fields=["last_verified_at", "primary_contact_name", "email", "mobile", "updated_at"])


@transaction.atomic
def create_subcontractor_contact(*, actor_membership, subcontractor_id, cleaned_data, request=None):
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    data = dict(cleaned_data)
    if data.get("is_primary") and data.get("is_active", True):
        SourcingSubcontractorContact.objects.for_company(obj.company).filter(subcontractor=obj, is_primary=True).update(is_primary=False)
    contact = SourcingSubcontractorContact(company=obj.company, subcontractor=obj, **data)
    contact.save()
    _sync_primary(obj, contact)
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.contact_created", after=_contact_snapshot(contact), request=request)
    return contact


@transaction.atomic
def update_subcontractor_contact(*, actor_membership, subcontractor_id, contact_id, cleaned_data, request=None):
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    contact = SourcingSubcontractorContact.objects.select_for_update().for_company(obj.company).get(pk=contact_id, subcontractor=obj)
    before = _contact_snapshot(contact)
    data = dict(cleaned_data)
    if data.get("is_primary") and data.get("is_active", True):
        SourcingSubcontractorContact.objects.for_company(obj.company).filter(subcontractor=obj, is_primary=True).exclude(pk=contact.pk).update(is_primary=False)
    for field, value in data.items():
        setattr(contact, field, value)
    if not contact.is_active:
        contact.is_primary = False
    contact.save()
    _sync_primary(obj, contact)
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.contact_updated", before=before, after=_contact_snapshot(contact), request=request)
    return contact


@transaction.atomic
def deactivate_subcontractor_contact(*, actor_membership, subcontractor_id, contact_id, request=None):
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    contact = SourcingSubcontractorContact.objects.select_for_update().for_company(obj.company).get(pk=contact_id, subcontractor=obj)
    before = _contact_snapshot(contact)
    contact.is_active = False
    was_primary = contact.is_primary
    contact.is_primary = False
    contact.save(update_fields=["is_active", "is_primary", "updated_at"])
    if was_primary:
        obj.primary_contact_name = ""
        obj.last_verified_at = None
        obj.save(update_fields=["primary_contact_name", "last_verified_at", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.contact_deactivated", before=before, after=_contact_snapshot(contact), request=request)
    return contact


@transaction.atomic
def delete_subcontractor_contact(*, actor_membership, subcontractor_id, contact_id, request=None):
    obj = _current(actor_membership, subcontractor_id)
    _writable(obj)
    contact = SourcingSubcontractorContact.objects.select_for_update().for_company(obj.company).get(pk=contact_id, subcontractor=obj)
    before = _contact_snapshot(contact)
    if contact.is_primary and contact.is_active:
        obj.primary_contact_name = ""
        obj.last_verified_at = None
        obj.save(update_fields=["primary_contact_name", "last_verified_at", "updated_at"])
    _audit(subcontractor=obj, actor_membership=actor_membership, action="sourcing.subcontractor.contact_deleted", before=before, after=None, request=request)
    contact.delete()
