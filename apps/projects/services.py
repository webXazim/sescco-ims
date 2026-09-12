from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.permissions import membership_can_edit, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.accounts.models import CompanyMembership
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.lifecycle import LifecycleAction, record_lifecycle_action, require_lifecycle_action
from apps.core.trash import move_to_trash, restore_from_trash

from .models import Project


def _require_manage_inventory(membership: CompanyMembership) -> None:
    if not (
        membership_has_capability(membership, Capability.MANAGE_INVENTORY)
        or membership_can_edit(membership, Workspace.RENTAL)
    ):
        raise PermissionDenied("Project lifecycle authority is required for this action.")


def _project_for_membership(*, membership: CompanyMembership, identifier, for_update: bool = True, include_deleted: bool = False) -> Project:
    queryset = Project.objects.select_for_update() if for_update else Project.objects.all()
    queryset = queryset.filter(company=membership.company)
    if not include_deleted:
        queryset = queryset.filter(deleted_at__isnull=True)
    raw = str(identifier)
    if raw.isdigit():
        return queryset.get(pk=int(raw))
    return queryset.get(reference=identifier)


def project_snapshot(project: Project) -> dict[str, object]:
    return {
        "reference": str(project.reference),
        "code": project.code,
        "name": project.name,
        "status": project.status,
        "archive_previous_status": project.archive_previous_status,
        "archived_at": project.archived_at.isoformat() if project.archived_at else "",
        "archived_reason": project.archived_reason,
        "end_date": project.end_date.isoformat() if project.end_date else "",
        "deleted_at": project.deleted_at.isoformat() if project.deleted_at else "",
    }


@transaction.atomic
def archive_project(*, actor_membership: CompanyMembership, project_id, reason: str, request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = _project_for_membership(membership=actor_membership, identifier=project_id)
    if project.status == Project.Status.ARCHIVED and project.archived_at:
        return project
    decision = require_lifecycle_action(project, LifecycleAction.ARCHIVE, reason=reason)
    before = project_snapshot(project)
    project.archive_previous_status = project.status if project.status != Project.Status.ARCHIVED else project.archive_previous_status
    project.status = Project.Status.ARCHIVED
    project.archived_at = timezone.now()
    project.archived_reason = (reason or "").strip()
    project.updated_by = actor_membership.user
    project.full_clean()
    project.save(update_fields=("status", "archive_previous_status", "archived_at", "archived_reason", "updated_by", "updated_at"))
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.archived",
        metadata={
            "cascade_scope": "project_operations",
            "stock_records_with_balance": decision.evidence.get("quantity_bearing_stock", 0),
            "open_rental_assignments": decision.evidence.get("open_rental_assignments", 0),
            "previous_status": project.archive_previous_status,
        },
        request=request,
    )
    return project


@transaction.atomic
def restore_project_archive(*, actor_membership: CompanyMembership, project_id, reason: str = "", request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = _project_for_membership(membership=actor_membership, identifier=project_id)
    if project.status != Project.Status.ARCHIVED and not project.archived_at:
        return project
    decision = require_lifecycle_action(project, LifecycleAction.RESTORE)
    before = project_snapshot(project)
    previous_reason = project.archived_reason
    restored_status = project.archive_previous_status
    if restored_status not in {Project.Status.ACTIVE, Project.Status.ON_HOLD, Project.Status.COMPLETED}:
        restored_status = Project.Status.COMPLETED if project.end_date else Project.Status.ON_HOLD
    project.archived_at = None
    project.archived_reason = ""
    project.status = restored_status
    project.archive_previous_status = ""
    project.updated_by = actor_membership.user
    project.full_clean()
    project.save(update_fields=("status", "archive_previous_status", "archived_at", "archived_reason", "updated_by", "updated_at"))
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.archive_restored",
        metadata={
            "previous_archive_reason": previous_reason,
            "restored_status": project.status,
            "cascade_scope": "project_operations",
        },
        request=request,
    )
    return project


@transaction.atomic
def trash_unused_project(*, actor_membership: CompanyMembership, project_id, confirmation: str, reason: str, request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = _project_for_membership(membership=actor_membership, identifier=project_id)
    decision = require_lifecycle_action(project, LifecycleAction.DELETE, confirmation=confirmation, reason=reason)
    before = project_snapshot(project)
    move_to_trash(project, user=actor_membership.user, reason=reason)
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.moved_to_trash",
        metadata={
            "retention_days": 30,
            "cascade_scope": "project_operations",
            "stock_records_with_balance": decision.evidence.get("quantity_bearing_stock", 0),
            "open_rental_assignments": decision.evidence.get("open_rental_assignments", 0),
        },
        request=request,
    )
    return project


@transaction.atomic
def restore_project_trash(*, actor_membership: CompanyMembership, project_id, request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = _project_for_membership(membership=actor_membership, identifier=project_id, include_deleted=True)
    if not project.deleted_at:
        return project
    before = project_snapshot(project)
    if not restore_from_trash(project):
        from django.core.exceptions import ValidationError
        raise ValidationError({"project": "This Trash item has expired and can no longer be restored."})
    project.updated_by = actor_membership.user
    project.save(update_fields=("updated_by", "updated_at"))
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action="project.trash_restored",
        object_type="projects.Project", object_id=project.reference, object_label=str(project),
        actor_membership=actor_membership, before=before, after=project_snapshot(project),
        metadata={"retention_days": 30, "cascade_scope": "project_operations"}, request=request,
    )
    return project

