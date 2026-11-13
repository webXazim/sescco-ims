"""Atomic audited U03 task/category writes. No Inventory/Payroll/finance effects."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .models import PulseTask, PulseWorkCategory, PulseProgressUpdate, PulseBudgetRevision


_CATEGORY_FIELDS = ("name", "description", "sort_order", "progress_weight")
_TASK_FIELDS = ("category", "title", "description", "assigned_to", "priority",
                "status", "planned_start", "due_date", "sort_order", "progress_weight")


def _checked_project(actor, project_id, permission):
    view_requirement = {
        AccessPermission.PULSE_CATEGORIES_MANAGE: AccessPermission.PULSE_CATEGORIES_VIEW,
        AccessPermission.PULSE_TASKS_MANAGE: AccessPermission.PULSE_TASKS_VIEW,
    }.get(permission)
    required = (AccessPermission.PULSE_OVERVIEW_VIEW,
                AccessPermission.PULSE_PROJECTS_VIEW, permission)
    if view_requirement:
        required += (view_requirement,)
    if not all(membership_has_permission(actor, p) for p in required):
        raise PermissionDenied("You do not have Project Pulse work management authority.")
    project = get_object_or_404(Project.objects.select_for_update().filter(
        pk=project_id, company_id=actor.company_id, deleted_at__isnull=True,
    ))
    if not membership_allows_project(actor, project):
        raise PermissionDenied("This project is outside your assigned project scope.")
    if project.status != Project.Status.ACTIVE or project.archived_at is not None:
        raise ValidationError("Tasks and categories can only be changed while the project is active.")
    return project


def _category(project, category_id, *, active=False):
    qs = PulseWorkCategory.objects.select_for_update().filter(project=project)
    if active:
        qs = qs.filter(archived_at__isnull=True)
    return get_object_or_404(qs, pk=category_id)


def _task(project, task_id, *, active=False):
    qs = PulseTask.objects.select_for_update().select_related("category").filter(category__project=project)
    if active:
        qs = qs.filter(archived_at__isnull=True, category__archived_at__isnull=True)
    return get_object_or_404(qs, pk=task_id)


def _category_snapshot(row):
    return {"name": row.name, "code": row.code, "description": row.description,
            "order": row.sort_order, "progress_weight": str(row.progress_weight),
            "archived": bool(row.archived_at)}


def _task_snapshot(row):
    return {"category_id": row.category_id, "title": row.title,
            "description": row.description, "assigned_membership": str(row.assigned_to_id or ""),
            "priority": row.priority, "status": row.status,
            "progress_percent": row.progress_percent, "progress_weight": str(row.progress_weight),
            "planned_start": str(row.planned_start or ""), "due_date": str(row.due_date or ""),
            "order": row.sort_order, "archived": bool(row.archived_at)}


def _audit(project, actor, action, obj, before, after, request=None):
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action=action,
        object_type=f"project_pulse.{type(obj).__name__}", object_id=obj.pk,
        object_label=f"{project.code} · {obj}", actor_membership=actor,
        before=before or {}, after=after, request=request,
    )


@transaction.atomic
def save_category(*, actor, project_id, data, category_id=None, request=None):
    project = _checked_project(actor, project_id, AccessPermission.PULSE_CATEGORIES_MANAGE)
    row = _category(project, category_id, active=True) if category_id is not None else PulseWorkCategory(project=project, created_by=actor)
    before = _category_snapshot(row) if row.pk else None
    for field in _CATEGORY_FIELDS:
        if field in data:
            setattr(row, field, data[field])
    row.save()
    _audit(project, actor, "pulse.category.updated" if before else "pulse.category.created",
           row, before, _category_snapshot(row), request)
    return row


@transaction.atomic
def set_category_archive(*, actor, project_id, category_id, archive, request=None):
    project = _checked_project(actor, project_id, AccessPermission.PULSE_CATEGORIES_MANAGE)
    row = _category(project, category_id)
    if bool(row.archived_at) == bool(archive):
        raise ValidationError("Work category already has that archive status.")
    if archive and row.tasks.filter(archived_at__isnull=True).exists():
        raise ValidationError("Archive the category's tasks first to avoid hiding active records.")
    if archive and PulseBudgetRevision.objects.filter(category=row, status=PulseBudgetRevision.Status.PENDING).exists():
        raise ValidationError("Review the pending category budget before archiving this category.")
    before = _category_snapshot(row)
    row.archived_at = timezone.now() if archive else None
    row.save()
    _audit(project, actor, "pulse.category.archived" if archive else "pulse.category.restored",
           row, before, _category_snapshot(row), request)
    return row


@transaction.atomic
def save_task(*, actor, project_id, data, task_id=None, request=None):
    project = _checked_project(actor, project_id, AccessPermission.PULSE_TASKS_MANAGE)
    row = _task(project, task_id, active=True) if task_id is not None else PulseTask(created_by=actor)
    before = _task_snapshot(row) if row.pk else None
    old_status = row.status if row.pk else PulseTask.Status.NOT_STARTED
    old_percent = row.progress_percent if row.pk else 0
    for field in _TASK_FIELDS:
        if field in data:
            setattr(row, field, data[field])
    # U03's status editor remains usable. Any status-driven percentage adjustment
    # creates an explicit, immutable progress-history row.
    if row.status == PulseTask.Status.COMPLETED:
        row.progress_percent = 100
    elif row.status == PulseTask.Status.NOT_STARTED or (old_percent == 100 and row.status != PulseTask.Status.COMPLETED):
        row.progress_percent = 0
    if row.category.project_id != project.pk or row.category.archived_at is not None:
        raise ValidationError({"category": "Choose an active category within this project."})
    row.save()
    if row.status != old_status or row.progress_percent != old_percent:
        PulseProgressUpdate.objects.create(
            task=row, previous_percent=old_percent, new_percent=row.progress_percent,
            previous_status=old_status, new_status=row.status,
            note="Status updated through the task editor.", updated_by=actor,
        )
    _audit(project, actor, "pulse.task.updated" if before else "pulse.task.created",
           row, before, _task_snapshot(row), request)
    return row


@transaction.atomic
def set_task_archive(*, actor, project_id, task_id, archive, request=None):
    project = _checked_project(actor, project_id, AccessPermission.PULSE_TASKS_MANAGE)
    row = _task(project, task_id)
    if bool(row.archived_at) == bool(archive):
        raise ValidationError("Task already has that archive status.")
    if not archive and row.category.archived_at is not None:
        raise ValidationError("Restore the parent work category before restoring the task.")
    before = _task_snapshot(row)
    row.archived_at = timezone.now() if archive else None
    row.save()
    _audit(project, actor, "pulse.task.archived" if archive else "pulse.task.restored",
           row, before, _task_snapshot(row), request)
    return row
