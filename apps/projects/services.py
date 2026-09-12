from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.accounts.models import CompanyMembership
from apps.core.services.lifecycle import LifecycleAction, record_lifecycle_action, require_lifecycle_action
from apps.core.trash import move_to_trash

from .models import Project


def _require_manage_inventory(membership: CompanyMembership) -> None:
    if not membership_has_capability(membership, Capability.MANAGE_INVENTORY):
        raise PermissionDenied("Inventory management authority is required for this project lifecycle action.")


def project_snapshot(project: Project) -> dict[str, object]:
    return {
        "reference": str(project.reference),
        "code": project.code,
        "name": project.name,
        "status": project.status,
        "archived_at": project.archived_at.isoformat() if project.archived_at else "",
        "archived_reason": project.archived_reason,
        "end_date": project.end_date.isoformat() if project.end_date else "",
        "deleted_at": project.deleted_at.isoformat() if project.deleted_at else "",
    }


@transaction.atomic
def archive_project(*, actor_membership: CompanyMembership, project_id, reason: str, request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = Project.objects.select_for_update().get(pk=project_id, company=actor_membership.company, deleted_at__isnull=True)
    if project.status == Project.Status.ARCHIVED and project.archived_at:
        return project
    decision = require_lifecycle_action(project, LifecycleAction.ARCHIVE, reason=reason)
    before = project_snapshot(project)
    project.status = Project.Status.ARCHIVED
    project.archived_at = timezone.now()
    project.archived_reason = (reason or "").strip()
    project.updated_by = actor_membership.user
    project.full_clean()
    project.save(update_fields=("status", "archived_at", "archived_reason", "updated_by", "updated_at"))
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.archived",
        request=request,
    )
    return project


@transaction.atomic
def restore_project_archive(*, actor_membership: CompanyMembership, project_id, reason: str = "", request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = Project.objects.select_for_update().get(pk=project_id, company=actor_membership.company, deleted_at__isnull=True)
    if project.status != Project.Status.ARCHIVED and not project.archived_at:
        return project
    decision = require_lifecycle_action(project, LifecycleAction.RESTORE)
    before = project_snapshot(project)
    previous_reason = project.archived_reason
    project.archived_at = None
    project.archived_reason = ""
    # Restore to a safe non-operational state. The user explicitly resumes/reactivates later.
    project.status = Project.Status.COMPLETED if project.end_date else Project.Status.ON_HOLD
    project.updated_by = actor_membership.user
    project.full_clean()
    project.save(update_fields=("status", "archived_at", "archived_reason", "updated_by", "updated_at"))
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.archive_restored",
        metadata={"previous_archive_reason": previous_reason, "restored_status": project.status},
        request=request,
    )
    return project


@transaction.atomic
def trash_unused_project(*, actor_membership: CompanyMembership, project_id, confirmation: str, reason: str, request: HttpRequest | None = None) -> Project:
    _require_manage_inventory(actor_membership)
    project = Project.objects.select_for_update().get(pk=project_id, company=actor_membership.company, deleted_at__isnull=True)
    decision = require_lifecycle_action(project, LifecycleAction.DELETE, confirmation=confirmation)
    before = project_snapshot(project)
    move_to_trash(project, user=actor_membership.user, reason=reason)
    record_lifecycle_action(
        instance=project,
        decision=decision,
        actor_membership=actor_membership,
        before=before,
        after=project_snapshot(project),
        reason=reason,
        audit_action="project.trashed_unused",
        metadata={"guard": "unused-master-only", "retention_days": 30},
        request=request,
    )
    return project
