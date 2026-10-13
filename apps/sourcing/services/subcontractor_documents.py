"""Protected reference-only subcontractor qualification files.

Uploads are not operational Documents. No media URL is ever exposed: all reads
pass a tenant-scoped, permission-checked Sourcing Django endpoint.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import hashlib

from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from ..models import SourcingSubcontractorDocument, SubcontractorQualificationReview
from .subcontractors import _audit, _current, _writable

MAX_BYTES = 10 * 1024 * 1024


def inspect_upload(upload):
    if not upload or not (0 < upload.size <= MAX_BYTES):
        raise ValidationError({"upload": "File must be between 1 byte and 10 MB."})
    ext = Path(upload.name or "").suffix.casefold()
    prefix = upload.read(16)
    upload.seek(0)
    if prefix.startswith(b"%PDF-") and ext == ".pdf":
        return ".pdf", "application/pdf"
    if prefix.startswith(b"\x89PNG\r\n\x1a\n") and ext == ".png":
        return ".png", "image/png"
    if prefix.startswith(b"\xff\xd8\xff") and ext in {".jpg", ".jpeg"}:
        return ".jpg", "image/jpeg"
    raise ValidationError({"upload": "Upload a PDF, PNG or JPEG with a matching file extension."})


def _document_snapshot(doc):
    """Reference metadata only: never record private path or file bytes in audit."""
    return {
        "id": str(doc.pk), "kind": doc.kind, "title": doc.title,
        "reference_number": doc.reference_number, "issuer": doc.issuer,
        "issued_on": doc.issued_on.isoformat() if doc.issued_on else None,
        "expires_on": doc.expires_on.isoformat() if doc.expires_on else None,
        "review_status": doc.review_status, "reviewed_at": doc.reviewed_at.isoformat() if doc.reviewed_at else None,
        "review_note": doc.review_note, "sha256": doc.sha256,
        "file_size": doc.file_size, "original_name": doc.original_name,
    }


def _document(actor_membership, subcontractor, document_id):
    return SourcingSubcontractorDocument.objects.select_for_update().for_company(
        actor_membership.company
    ).get(pk=document_id, subcontractor=subcontractor)


@transaction.atomic
def create_document(*, actor_membership, subcontractor_id, cleaned_data, upload, request=None):
    sub = _current(actor_membership, subcontractor_id)
    _writable(sub)
    if upload is None:
        raise ValidationError({"upload": "Select a qualification file."})
    ext, content_type = inspect_upload(upload)
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    key = default_storage.save(
        f"subcontractor-qualifications/{sub.company_id}/{uuid4().hex}{ext}", upload,
    )
    try:
        doc = SourcingSubcontractorDocument(
            company=sub.company, subcontractor=sub, **cleaned_data,
            original_name=Path(upload.name).name[:255], storage_key=key,
            content_type=content_type, file_size=upload.size, sha256=digest.hexdigest(),
        )
        doc.save()
        _audit(subcontractor=sub, actor_membership=actor_membership,
               action="sourcing.subcontractor.qualification_added", after=_document_snapshot(doc), request=request)
        return doc
    except Exception:
        default_storage.delete(key)
        raise


@transaction.atomic
def update_document(*, actor_membership, subcontractor_id, document_id, cleaned_data, request=None):
    sub = _current(actor_membership, subcontractor_id)
    _writable(sub)
    doc = _document(actor_membership, sub, document_id)
    before = _document_snapshot(doc)
    for field, value in cleaned_data.items():
        setattr(doc, field, value)
    # Changed qualification information is no longer considered reviewed.
    if any(before[field] != _document_snapshot(doc)[field] for field in
           ("kind", "title", "reference_number", "issuer", "issued_on", "expires_on")):
        doc.review_status = SubcontractorQualificationReview.PENDING
        doc.reviewed_by = None
        doc.reviewed_at = None
        doc.review_note = ""
    doc.save()
    _audit(subcontractor=sub, actor_membership=actor_membership,
           action="sourcing.subcontractor.qualification_updated", before=before,
           after=_document_snapshot(doc), request=request)
    return doc


@transaction.atomic
def review_document(*, actor_membership, subcontractor_id, document_id, status, note, request=None):
    if status not in {SubcontractorQualificationReview.APPROVED, SubcontractorQualificationReview.REJECTED}:
        raise ValidationError({"status": "Choose Reviewed/Accepted or Rejected."})
    note = str(note or "").strip()
    if not note or len(note) > 500:
        raise ValidationError({"note": "Provide a review note (maximum 500 characters)."})
    sub = _current(actor_membership, subcontractor_id)
    _writable(sub)
    doc = _document(actor_membership, sub, document_id)
    if status == SubcontractorQualificationReview.APPROVED and doc.expired:
        raise ValidationError("An expired qualification cannot be accepted. Upload a valid document.")
    before = _document_snapshot(doc)
    doc.review_status = status
    doc.reviewed_at = timezone.now()
    doc.reviewed_by = actor_membership.user
    doc.review_note = note
    doc.save(update_fields=["review_status", "reviewed_at", "reviewed_by", "review_note", "updated_at"])
    _audit(subcontractor=sub, actor_membership=actor_membership,
           action="sourcing.subcontractor.qualification_reviewed", before=before,
           after=_document_snapshot(doc), request=request)
    return doc


@transaction.atomic
def delete_document(*, actor_membership, subcontractor_id, document_id, confirmation, request=None):
    sub = _current(actor_membership, subcontractor_id)
    _writable(sub)
    doc = _document(actor_membership, sub, document_id)
    if str(confirmation or "").strip().casefold() != doc.title.casefold():
        raise ValidationError({"confirmation": f"Type {doc.title} to confirm."})
    before = _document_snapshot(doc)
    key = doc.storage_key
    _audit(subcontractor=sub, actor_membership=actor_membership,
           action="sourcing.subcontractor.qualification_deleted", before=before,
           request=request)
    doc.delete()
    transaction.on_commit(lambda: default_storage.delete(key))
    return before["title"]
