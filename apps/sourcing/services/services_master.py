"""Atomic, audited operations for the independent Sourcing Services master."""
from __future__ import annotations

from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from ..models import SourcingService, SourcingSubcontractorService


def suggest_service_code() -> str:
    return f"SRV-{uuid4().hex[:8].upper()}"


def _snapshot(service: SourcingService) -> dict[str, object]:
    return {
        "code": service.code, "name": service.name, "category": service.category,
        "defaultRateBasis": service.default_rate_basis,
        "aliases": list(service.aliases or []), "description": service.description,
        "notes": service.notes, "isActive": service.is_active,
    }


def _audit(*, service, actor_membership, action, before=None, after=None, metadata=None, request=None):
    return record_audit_event(
        company=service.company, area=AuditArea.SOURCING, action=action,
        object_type="sourcing.SourcingService", object_id=service.pk,
        object_label=f"{service.code} · {service.name}", actor_membership=actor_membership,
        before=before, after=after, metadata=metadata, request=request,
    )


@transaction.atomic
def create_service(*, actor_membership, cleaned_data, request=None) -> SourcingService:
    data = dict(cleaned_data)
    if not str(data.get("code") or "").strip():
        data["code"] = suggest_service_code()
    service = SourcingService(company=actor_membership.company, **data)
    service.save()  # full_clean performs normalized name/alias collision checks
    _audit(service=service, actor_membership=actor_membership,
           action="sourcing.service.created", after=_snapshot(service), request=request)
    return service


@transaction.atomic
def update_service(*, actor_membership, service_id, cleaned_data, request=None) -> SourcingService:
    service = SourcingService.objects.select_for_update().for_company(actor_membership.company).get(pk=service_id)
    before = _snapshot(service)
    for field, value in cleaned_data.items():
        setattr(service, field, value)
    service.save()
    _audit(service=service, actor_membership=actor_membership,
           action="sourcing.service.updated", before=before, after=_snapshot(service), request=request)
    return service


@transaction.atomic
def set_service_active(*, actor_membership, service_id, is_active, request=None) -> SourcingService:
    service = SourcingService.objects.select_for_update().for_company(actor_membership.company).get(pk=service_id)
    before = _snapshot(service)
    service.is_active = bool(is_active)
    service.save(update_fields=["is_active", "updated_at"])
    _audit(service=service, actor_membership=actor_membership,
           action="sourcing.service.activated" if service.is_active else "sourcing.service.deactivated",
           before=before, after=_snapshot(service), request=request)
    return service


@transaction.atomic
def delete_service(*, actor_membership, service_id, confirmation, request=None):
    """Prevent deleting a service while ANY subcontractor capability uses it."""
    service = SourcingService.objects.select_for_update().for_company(actor_membership.company).get(pk=service_id)
    if str(confirmation or "").strip().casefold() != service.code.casefold():
        raise ValidationError({"confirmation": f"Type {service.code} to confirm permanent deletion."})
    if SourcingSubcontractorService.objects.for_company(service.company).filter(service=service).exists():
        raise ValidationError("This Service is in use by subcontractors. Mark it Inactive instead.")
    before = _snapshot(service)
    _audit(service=service, actor_membership=actor_membership,
           action="sourcing.service.deleted", before=before, after=None,
           metadata={"permanent": True, "cascadeServiceOffers": 0}, request=request)
    label = service.name
    service.delete()
    return {"label": label}
