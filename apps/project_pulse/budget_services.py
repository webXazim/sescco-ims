"""U07: standalone, versioned category budgets and approved-cost comparisons.

This service never reads or writes Payroll or Inventory records. All budget data
remains confidential to users with explicit budget-view permission.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .expense_services import expense_rollups
from .models import PulseBudgetRevision, PulseWorkCategory


ZERO = Decimal("0.00")


def _authorized(actor, project_id, permission, *, writable=False):
    needed = (AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
              AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW,
              AccessPermission.PULSE_BUDGETS_VIEW, permission)
    if not all(membership_has_permission(actor, p) for p in needed):
        raise PermissionDenied("This access profile cannot access category budgets.")
    qs = Project.objects.filter(pk=project_id, company_id=actor.company_id, deleted_at__isnull=True)
    if writable:
        qs = qs.select_for_update()
    project = get_object_or_404(qs)
    if not membership_allows_project(actor, project):
        raise PermissionDenied("Project is outside the user's authorized project scope.")
    if writable and (project.status != Project.Status.ACTIVE or project.archived_at):
        raise ValidationError("Budgets may be changed only while a project is active.")
    return project


def _amount(value):
    try:
        amount = Decimal(str(value))
    except (ValueError, InvalidOperation, TypeError):
        raise ValidationError("Enter a valid budget amount in SAR.")
    if (not amount.is_finite() or amount < 0 or
            amount.as_tuple().exponent < -2 or amount >= Decimal("1000000000000")):
        raise ValidationError("Enter a nonnegative budget below SAR 1 trillion, with at most two decimals.")
    return amount


def _audit(project, actor, action, revision, request=None):
    # Never leak amounts/revision reasons/decision notes to general audit viewers.
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action=action,
        object_type="project_pulse.PulseBudgetRevision", object_id=revision.pk,
        object_label=f"{project.code} · Budget revision {revision.pk}",
        actor_membership=actor, before={}, after={}, metadata={}, request=request,
    )


@transaction.atomic
def propose_budget(*, actor, project_id, category_id, amount, reason, request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_BUDGETS_MANAGE, writable=True)
    category = get_object_or_404(PulseWorkCategory.objects.select_for_update(), pk=category_id, project=project)
    if category.archived_at:
        raise ValidationError("Restore this work category before proposing a budget.")
    amount = _amount(amount)
    reason = " ".join((reason or "").split())
    if not reason or len(reason) > 500:
        raise ValidationError("Enter a budget reason (up to 500 characters).")
    rows = PulseBudgetRevision.objects.filter(category=category)
    if rows.filter(status=PulseBudgetRevision.Status.PENDING).exists():
        raise ValidationError("This category already has a pending budget revision; review it first.")
    latest = rows.order_by("-revision_number").values_list("revision_number", flat=True).first() or 0
    revision = PulseBudgetRevision(
        category=category, revision_number=latest + 1, amount=amount,
        reason=reason, submitted_by=actor,
    )
    revision.save()
    _audit(project, actor, "pulse.budget.proposed", revision, request)
    return revision


@transaction.atomic
def review_budget(*, actor, project_id, revision_id, approve, note="", request=None):
    project = _authorized(actor, project_id, AccessPermission.PULSE_BUDGETS_APPROVE, writable=True)
    revision = get_object_or_404(
        PulseBudgetRevision.objects.select_for_update().select_related("category", "submitted_by"),
        pk=revision_id, category__project=project,
    )
    if revision.category.archived_at:
        raise ValidationError("Restore the work category before reviewing its budget.")
    if revision.status != PulseBudgetRevision.Status.PENDING:
        raise ValidationError("Only pending budget revisions can be reviewed.")
    if actor.pk == revision.submitted_by_id and actor.role != AccessRole.OWNER:
        raise PermissionDenied("Non-owners cannot approve their own budget proposals.")
    note = " ".join((note or "").split())
    if len(note) > 500 or (not approve and not note):
        raise ValidationError("Rejections require a reason; review notes have a 500-character limit.")
    revision.status = PulseBudgetRevision.Status.APPROVED if approve else PulseBudgetRevision.Status.REJECTED
    revision.reviewed_by = actor
    revision.reviewed_at = timezone.now()
    revision.review_note = note
    revision.save()
    _audit(project, actor, "pulse.budget.approved" if approve else "pulse.budget.rejected", revision, request)
    return revision


def budget_rollups(project):
    """Versioned approved budgets compared with *approved* non-voided costs.

    All categories, including archived, retain their approved budgets/costs.
    Active categories without approved budgets are explicitly counted as missing;
    do not misrepresent their absent budget as an approved zero budget.
    """
    categories = list(PulseWorkCategory.objects.filter(project=project).order_by("sort_order", "name", "pk"))
    revisions = PulseBudgetRevision.objects.filter(category__project=project).order_by("category_id", "-revision_number")
    current, pending = {}, {}
    for rev in revisions:
        if rev.status == PulseBudgetRevision.Status.APPROVED and rev.category_id not in current:
            current[rev.category_id] = rev
        if rev.status == PulseBudgetRevision.Status.PENDING:
            pending[rev.category_id] = rev

    expenses = expense_rollups(project)
    actual_by_category = expenses["approved_by_work_category"]
    total_budget = ZERO
    budgeted_actual_total = ZERO
    unbudgeted_actual_total = ZERO
    overrun_total = ZERO
    unbudgeted_active = 0
    warning_count = 0
    entries = []
    for category in categories:
        rev = current.get(category.pk)
        amount = rev.amount if rev else None
        actual = actual_by_category.get(category.pk, ZERO)
        remaining = amount - actual if amount is not None else None
        utilization = (actual * Decimal("100.00") / amount).quantize(Decimal("0.01")) if amount else None
        over_budget = amount is not None and actual > amount
        if rev:
            total_budget += amount
            budgeted_actual_total += actual
        else:
            unbudgeted_actual_total += actual
        if over_budget:
            overrun_total += actual - amount
            warning_count += 1
        if not rev and category.archived_at is None:
            unbudgeted_active += 1
        entries.append({
            "category": category, "revision": rev, "pending": pending.get(category.pk),
            "amount": amount, "actual": actual, "remaining": remaining,
            "utilization": utilization, "over_budget": over_budget,
        })
    return {
        "rows": entries,
        "approved_budget_total": total_budget,
        "approved_cost_total": expenses["approved_total"],
        "remaining_total": total_budget - expenses["approved_total"],
        # A scoped, meaningful balance that excludes costs of categories where
        # the budget has not been established. Do not silently treat missing as 0.
        "balance_on_approved_budgets": total_budget - budgeted_actual_total,
        "unbudgeted_approved_cost": unbudgeted_actual_total,
        "unbudgeted_active_count": unbudgeted_active,
        "over_budget_count": warning_count,
        "total_category_overrun": overrun_total,
        "is_complete": unbudgeted_active == 0 and unbudgeted_actual_total == ZERO and bool(categories),
        "category_count": len(categories),
    }
