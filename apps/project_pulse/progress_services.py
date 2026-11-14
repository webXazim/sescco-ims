"""Audited operational progress updates and completed-work count rollups."""
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .models import PulseProgressUpdate, PulseProjectTeamMember, PulseTask, PulseWorkCategory


_ZERO = Decimal("0")
_TENTH = Decimal("0.1")


def can_update_task_progress(actor, task):
    """Scheduled work belongs to the project, not to an individual assignee.

    The Project Pulse progress-update permission plus project scope grants
    update authority; a personal task assignment must not be required.
    """
    if actor is None or not all(membership_has_permission(actor, p) for p in (
        AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
        AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW,
        AccessPermission.PULSE_PROGRESS_UPDATE,
    )):
        return False
    return bool(actor.company_id == task.category.project.company_id
                and membership_allows_project(actor, task.category.project))


def _percent(numerator, denominator):
    if not denominator:
        return Decimal("0.0")
    return ((numerator / denominator).quantize(_TENTH, rounding=ROUND_HALF_UP))


def calculate_progress(project_ids, *, today=None):
    """Count-based project execution progress, never financial or manually weighted.

    For each active execution category: completed non-cancelled, non-archived
    scheduled works / eligible scheduled works. Empty categories display 0%.
    Every active category, including an empty one, contributes equally to the
    project average. Archived categories and cancelled/archived works are
    excluded. Historical partial task percentages are ignored.
    """
    ids = list(dict.fromkeys(project_ids))
    if not ids:
        return {}, {}
    today = today or timezone.localdate()
    rows = list(PulseWorkCategory.objects.filter(
        project_id__in=ids, archived_at__isnull=True,
    ).values("id", "project_id"))
    projects = {pk: {
        "percent": Decimal("0.0"), "has_work": False,
        "task_count": 0, "completed_count": 0, "overdue_count": 0,
        "category_count": 0, "measured_categories": 0,
        "_category_percent_sum": _ZERO,
    } for pk in ids}
    cats = {}
    for cat in rows:
        cats[cat["id"]] = {
            "id": cat["id"], "project_id": cat["project_id"],
            "percent": Decimal("0.0"), "has_work": False,
            "task_count": 0, "completed_count": 0, "overdue_count": 0,
        }
        projects[cat["project_id"]]["category_count"] += 1
    if cats:
        for task in PulseTask.objects.filter(
            category_id__in=cats, archived_at__isnull=True,
        ).exclude(status=PulseTask.Status.CANCELLED).values(
            "category_id", "status", "due_date"
        ):
            category = cats[task["category_id"]]
            completed = task["status"] == PulseTask.Status.COMPLETED
            category["task_count"] += 1
            if completed:
                category["completed_count"] += 1
            if task["due_date"] and task["due_date"] < today and not completed:
                category["overdue_count"] += 1
    for category in cats.values():
        project = projects[category["project_id"]]
        category["has_work"] = category["task_count"] > 0
        if category["has_work"]:
            project["measured_categories"] += 1
        category["percent"] = _percent(
            Decimal(category["completed_count"] * 100), Decimal(category["task_count"])
        )
        project["task_count"] += category["task_count"]
        project["completed_count"] += category["completed_count"]
        project["overdue_count"] += category["overdue_count"]
        # Full precision before project-level rounding; include empty categories.
        if category["task_count"]:
            project["_category_percent_sum"] += (
                Decimal(category["completed_count"] * 100) / Decimal(category["task_count"])
            )
    for project in projects.values():
        project["has_work"] = project["task_count"] > 0
        project["percent"] = _percent(
            project.pop("_category_percent_sum"), Decimal(project["category_count"])
        )
    return projects, cats


@transaction.atomic
def record_progress(*, actor, project_id, task_id, progress_percent, status, note="", request=None):
    """Atomic progress edit; project lock serializes against task edits/archives."""
    required = (AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
                AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW,
                AccessPermission.PULSE_PROGRESS_UPDATE)
    if not all(membership_has_permission(actor, p) for p in required):
        raise PermissionDenied("Progress update permission is required.")
    project = get_object_or_404(Project.objects.select_for_update().filter(
        pk=project_id, company_id=actor.company_id, deleted_at__isnull=True,
    ))
    if not membership_allows_project(actor, project):
        raise PermissionDenied("Project is outside your assigned scope.")
    if project.status != Project.Status.ACTIVE or project.archived_at is not None:
        raise ValidationError("Progress changes are disabled unless the project is active.")
    task = get_object_or_404(PulseTask.objects.select_for_update().select_related(
        "category__project"
    ), pk=task_id, category__project=project)
    if task.archived_at is not None or task.category.archived_at is not None:
        raise ValidationError("Archived tasks cannot be updated.")
    if not can_update_task_progress(actor, task):
        raise PermissionDenied("You are not authorized to update scheduled works in this project.")
    try:
        percentage = int(progress_percent)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError({"progress_percent": "Enter a whole number from 0 to 100."}) from exc
    if str(progress_percent).strip() != str(percentage) or not 0 <= percentage <= 100:
        raise ValidationError({"progress_percent": "Enter a whole number from 0 to 100."})
    if status not in PulseTask.Status.values:
        raise ValidationError({"status": "Invalid task status."})
    note = (note or "").strip()
    if len(note) > 2000:
        raise ValidationError({"note": "Progress note must be 2,000 characters or fewer."})
    before_status, before_percent = task.status, task.progress_percent
    task.status, task.progress_percent = status, percentage
    task.full_clean()
    if before_status == status and before_percent == percentage and not note:
        raise ValidationError("Provide a progress change or a note before saving.")
    task.save(update_fields=["status", "progress_percent", "updated_at"])
    update = PulseProgressUpdate.objects.create(
        task=task, previous_percent=before_percent, new_percent=percentage,
        previous_status=before_status, new_status=status, note=note, updated_by=actor,
    )
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action="pulse.task.progress_updated",
        object_type="project_pulse.PulseTask", object_id=task.pk,
        object_label=f"{project.code} · {task.title}", actor_membership=actor,
        before={"status": before_status, "progress_percent": before_percent},
        after={"status": status, "progress_percent": percentage, "note": note, "progress_update_id": update.pk},
        request=request,
    )
    return update
