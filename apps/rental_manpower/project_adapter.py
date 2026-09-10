from __future__ import annotations

from django.core.exceptions import ValidationError

from apps.projects.contracts import (
    project_for_company,
    projects_for_company as shared_projects_for_company,
    validate_project_work_date,
)
from apps.projects.models import Project


def rental_project_for_company(*, company, identifier, for_update: bool = False, require_active: bool = False) -> Project:
    """Resolve a Rental API project identifier against the canonical shared Project.

    Rental APIs expose ``Project.reference`` UUIDs. Existing Inventory foreign keys continue using
    the integer Project primary key internally; this adapter is the only boundary that translates
    those identities for Rental Manpower services/selectors.
    """

    project = project_for_company(
        company=company,
        identifier=identifier,
        for_update=for_update,
        include_deleted=False,
    )
    if require_active and not project.accepts_rental_assignment:
        raise ValidationError({"project": "Choose an Active project for rental manpower activity."})
    return project


def rental_projects_for_company(*, company, query: str = "", status: str = ""):
    return shared_projects_for_company(company=company, query=query, status=status, include_deleted=False)


def validate_rental_project_date(*, project: Project, work_date, require_active: bool = True) -> None:
    validate_project_work_date(project=project, work_date=work_date, require_active=require_active)


def project_public_id(project: Project) -> str:
    return str(project.reference)
