from __future__ import annotations

import uuid
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Q, QuerySet

from .models import Project

# Rental Manpower will import this shared status authority in Upgrade 7 instead of carrying
# a second ProjectStatus enum/model. Keep this alias in the projects domain.
ProjectStatus = Project.Status


def projects_for_company(*, company, query: str = "", status: str = "", include_deleted: bool = False) -> QuerySet[Project]:
    queryset = Project.objects.for_company(company)
    if not include_deleted:
        queryset = queryset.filter(deleted_at__isnull=True)
    query = (query or "").strip()
    if query:
        queryset = queryset.filter(
            Q(code__icontains=query)
            | Q(name__icontains=query)
            | Q(client_name__icontains=query)
            | Q(location__icontains=query)
            | Q(manager_name__icontains=query)
        )
    if status:
        if status not in Project.Status.values:
            raise ValidationError({"status": "Unknown project status."})
        queryset = queryset.filter(status=status)
    return queryset.order_by("-start_date", "code")


def project_for_company(*, company, identifier, for_update: bool = False, include_deleted: bool = False) -> Project:
    """Resolve one canonical project without allowing a cross-company identifier lookup.

    Public merged-module APIs use ``Project.reference`` (UUID). Integer PKs are still accepted
    internally for existing IMS code, and project codes remain accepted for legacy navigation.
    """

    queryset = Project.objects.for_company(company)
    if for_update:
        queryset = queryset.select_for_update()
    if not include_deleted:
        queryset = queryset.filter(deleted_at__isnull=True)

    if isinstance(identifier, Project):
        if identifier.company_id != company.pk or (identifier.deleted_at and not include_deleted):
            raise Project.DoesNotExist
        return identifier

    if isinstance(identifier, uuid.UUID):
        return queryset.get(reference=identifier)

    value = str(identifier or "").strip()
    if not value:
        raise Project.DoesNotExist
    try:
        return queryset.get(reference=uuid.UUID(value))
    except (ValueError, AttributeError, TypeError, Project.DoesNotExist):
        pass

    if value.isdigit():
        try:
            return queryset.get(pk=int(value))
        except Project.DoesNotExist:
            pass
    return queryset.get(code=value.upper())


def validate_project_work_date(*, project: Project, work_date: date, require_active: bool = True) -> None:
    """Shared operational-date guard used by Inventory/Payroll integration points."""

    if project.deleted_at is not None:
        raise ValidationError({"project": "The project is in Trash and cannot accept operational activity."})
    if require_active and project.status != Project.Status.ACTIVE:
        raise ValidationError({"project": "Choose an active project."})
    if project.start_date and work_date < project.start_date:
        raise ValidationError({"project": "The work date is before the project start date."})
    if project.end_date and work_date > project.end_date:
        raise ValidationError({"project": "The work date is after the project end date."})


def serialize_shared_project(project: Project) -> dict[str, object]:
    """Stable cross-module project payload used by the future Payroll API adapter."""

    return {
        "id": str(project.reference),
        "reference": str(project.reference),
        "code": project.code,
        "name": project.name,
        "client": project.client_name,
        "location": project.location,
        "startDate": project.start_date.isoformat() if project.start_date else "",
        "expectedCompletionDate": (
            project.expected_completion_date.isoformat() if project.expected_completion_date else ""
        ),
        "endDate": project.end_date.isoformat() if project.end_date else "",
        "manager": project.manager_name,
        "status": project.get_status_display(),
        "statusValue": project.status,
        "notes": project.notes,
        "acceptsInventory": project.accepts_stock_activity,
        "acceptsRentalAssignments": project.accepts_rental_assignment,
    }
