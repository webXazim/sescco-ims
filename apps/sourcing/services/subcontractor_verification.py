"""Explicit company-profile confirmation; never modifies service-offer freshness."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .subcontractors import _audit, _current, _snapshot, _writable
from ..models import SourcingEntityStatus, SourcingSubcontractorVerificationRevision
from ..models.base import clean_text


@transaction.atomic
def verify_subcontractor(*, actor_membership, subcontractor_id, contact_name, note, request=None):
    subcontractor = _current(actor_membership, subcontractor_id)
    _writable(subcontractor)
    if subcontractor.status != SourcingEntityStatus.ACTIVE:
        raise ValidationError("Activate the subcontractor before verifying the company profile.")
    contact_name = clean_text(contact_name)[:160]
    note = clean_text(note)[:500]
    if not contact_name:
        raise ValidationError({"contact_name": "Record who confirmed the company details."})
    if not note:
        raise ValidationError({"note": "Describe which company details were confirmed."})
    before = _snapshot(subcontractor)
    now = timezone.now()
    subcontractor.last_verified_at = now
    subcontractor.save(update_fields=["last_verified_at", "updated_at"])
    after = _snapshot(subcontractor)
    revision = SourcingSubcontractorVerificationRevision.objects.create(
        company=subcontractor.company, subcontractor=subcontractor,
        subcontractor_id_snapshot=subcontractor.pk, before=before, after=after,
        verified_at=now, actor=actor_membership.user,
        contact_name=contact_name, note=note,
    )
    _audit(
        subcontractor=subcontractor, actor_membership=actor_membership,
        action="sourcing.subcontractor.company_verified", before=before, after=after,
        metadata={"contactName": contact_name, "revisionId": str(revision.pk)},
        request=request,
    )
    return revision
