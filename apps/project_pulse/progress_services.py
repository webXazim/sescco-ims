"""Audited operational progress updates and deterministic weighted rollups.

No financial sources are used. Only active categories, active non-cancelled
work, and their strictly positive weights contribute to progress denominators.
"""
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
    """Authorized task managers or a current team manager/assignee only.

    Assignment alone must not grant permissions, and revoked assignments must
    not enable progress changes. This is rechecked under a transaction on POST.
    """
    if actor is None or not all(membership_has_permission(actor, p) for p in (
        AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
        AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW,
        AccessPermission.PULSE_PROGRESS_UPDATE,
    )):
        return False
    if actor.company_id != task.category.project.company_id or not membership_allows_project(actor, task.category.project):
        return False
    if membership_has_permission(actor, AccessPermission.PULSE_TASKS_MANAGE):
        return True
    if not PulseProjectTeamMember.objects.filter(
        project_id=task.category.project_id, membership_id=actor.pk, is_active=True
    ).exists():
        return False
    return bool(task.assigned_to_id == actor.pk or PulseProjectTeamMember.objects.filter(
        project_id=task.category.project_id, membership_id=actor.pk,
        is_active=True, role=PulseProjectTeamMember.Role.MANAGER,
    ).exists())


def _percent(numerator, denominator):
    if not denominator:
        return Decimal("0.0")
    return ((numerator / denominator).quantize(_TENTH, rounding=ROUND_HALF_UP))


def calculate_progress(project_ids, *, today=None):
    """Return (project_metrics, category_metrics) keyed by IDs.

    An empty project/category reports 0.0% and has_work=False. Archived and
    cancelled work is excluded from both numerator and denominator. No cache is
    persisted, so archive/restore, reweighting, and edits instantly recalculate.
    """
    ids = list(dict.fromkeys(project_ids))
    if not ids:
        return {}, {}
    today = today or timezone.localdate()
    categories = list(PulseWorkCategory.objects.filter(
        project_id__in=ids, archived_at__isnull=True,
    ).values("id", "project_id", "progress_weight"))
    cats = {}
    projects = {pk: {"percent": Decimal("0.0"), "has_work": False, "task_count": 0,
                     "completed_count": 0, "overdue_count": 0, "category_count": 0,
                     "measured_categories": 0, "_weighted_sum": _ZERO, "_weight_sum": _ZERO}
                for pk in ids}
    for cat in categories:
        cats[cat["id"]] = {"id": cat["id"], "project_id": cat["project_id"],
                           "percent": Decimal("0.0"), "has_work": False,
                           "task_count": 0, "completed_count": 0, "overdue_count": 0,
                           "_weighted_sum": _ZERO, "_weight_sum": _ZERO,
                           "weight": cat["progress_weight"]}
        projects[cat["project_id"]]["category_count"] += 1
    if cats:
        for task in PulseTask.objects.filter(
            category_id__in=cats, archived_at__isnull=True,
        ).exclude(status=PulseTask.Status.CANCELLED).values(
            "category_id", "status", "progress_percent", "progress_weight", "due_date"
        ):
            summary = cats[task["category_id"]]
            summary["task_count"] += 1
            summary["completed_count"] += task["status"] == PulseTask.Status.COMPLETED
            summary["overdue_count"] += bool(
                task["due_date"] and task["due_date"] < today and task["status"] != PulseTask.Status.COMPLETED
            )
            summary["_weighted_sum"] += task["progress_weight"] * Decimal(task["progress_percent"])
            summary["_weight_sum"] += task["progress_weight"]
    for cat in cats.values():
        project = projects[cat["project_id"]]
        cat["has_work"] = cat["task_count"] > 0
        cat["percent"] = _percent(cat["_weighted_sum"], cat["_weight_sum"])
        project["task_count"] += cat["task_count"]
        project["completed_count"] += cat["completed_count"]
        project["overdue_count"] += cat["overdue_count"]
        if cat["has_work"]:
            project["measured_categories"] += 1
            # Full-precision category average: avoid double-rounding project progress.
            project["_weighted_sum"] += cat["weight"] * (cat["_weighted_sum"] / cat["_weight_sum"])
            project["_weight_sum"] += cat["weight"]
        for key in ("_weighted_sum", "_weight_sum"):
            cat.pop(key)
    for project in projects.values():
        project["has_work"] = project["task_count"] > 0
        project["percent"] = _percent(project.pop("_weighted_sum"), project.pop("_weight_sum"))
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
        raise PermissionDenied("You may update only your assigned tasks unless you are an authorized project/task manager.")
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
