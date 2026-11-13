"""U05 standalone project-task expense ledger; no payroll or inventory integration."""
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.projects.models import Project

from .models import (PulseExpenseCategory, PulseExpenseEntry, PulseExpenseChange, PulseTask,
                     PulseExpensePayment, PulseExpenseAttachment)
from .private_storage import validate_expense_evidence
from apps.accounts.roles import AccessRole
from pathlib import Path


def _project(actor, project_id, permission, *, writable=True):
    needed = (AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW, permission)
    if permission == AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE:
        needed += (AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW,)
    if permission in (AccessPermission.PULSE_EXPENSES_MANAGE, AccessPermission.PULSE_EXPENSES_APPROVE,
                      AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE, AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE):
        needed += (AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW)
    if permission == AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE:
        needed += (AccessPermission.PULSE_EXPENSES_MANAGE,)
    if not all(membership_has_permission(actor, item) for item in needed):
        raise PermissionDenied("This access profile cannot manage project expenses.")
    project = get_object_or_404(Project.objects.select_for_update().filter(
        pk=project_id, company_id=actor.company_id, deleted_at__isnull=True
    ))
    if not membership_allows_project(actor, project):
        raise PermissionDenied("Project is outside the user's authorized scope.")
    if writable and (project.status != Project.Status.ACTIVE or project.archived_at):
        raise ValidationError("Expense records can be changed only for active projects.")
    return project


def _audit(project, actor, action, row, request=None, **metadata):
    # Security: avoid copying amounts, payee names or descriptions into the
    # shared audit stream where non-finance audit users may have access.
    record_audit_event(
        company=project.company, area=AuditArea.PROJECTS, action=action,
        object_type=f"project_pulse.{type(row).__name__}", object_id=row.pk,
        object_label=f"{project.code} · Expense record {row.pk}",
        actor_membership=actor, before={}, after={}, metadata=metadata,
        request=request,
    )


def _snapshot(row):
    return {
        "task_id": row.task_id,
        "expense_category_id": row.expense_category_id,
        "description": row.description,
        "amount_sar": str(row.amount),
        "expense_date": row.expense_date.isoformat(),
        "supplier_name": row.supplier_name,
        "reference": row.reference,
        "notes": row.notes,
        "voided_at": row.voided_at.isoformat() if row.voided_at else None,
        "void_reason": row.void_reason,
        "approval_status": row.approval_status,
        "review_note": row.review_note,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


def _expense_task(project, task_id, *, editable=True):
    task = get_object_or_404(PulseTask.objects.select_for_update().select_related("category"),
                             pk=task_id, category__project=project)
    if editable and (task.archived_at or task.category.archived_at):
        raise ValidationError("Cannot add or edit expenses for archived tasks or work categories.")
    return task


@transaction.atomic
def save_expense_category(*, actor, project_id, data, category_id=None, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE)
    if category_id is None:
        row = PulseExpenseCategory(project=project, created_by=actor)
    else:
        row = get_object_or_404(PulseExpenseCategory.objects.select_for_update(),
                                pk=category_id, project=project)
        if row.archived_at:
            raise ValidationError("Restore the expense category before editing.")
    for key in ("name", "description", "sort_order"):
        if key in data:
            setattr(row, key, data[key])
    row.save()
    _audit(project, actor, "pulse.expense_category.updated" if category_id else "pulse.expense_category.created",
           row, request)
    return row


@transaction.atomic
def archive_expense_category(*, actor, project_id, category_id, archive=True, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE)
    row = get_object_or_404(PulseExpenseCategory.objects.select_for_update(),
                            project=project, pk=category_id)
    if bool(row.archived_at) == bool(archive):
        raise ValidationError("This expense category already has that archive status.")
    row.archived_at = timezone.now() if archive else None
    row.save()
    _audit(project, actor, "pulse.expense_category.archived" if archive else "pulse.expense_category.restored",
           row, request)
    return row


@transaction.atomic
def save_expense(*, actor, project_id, task_id, data, expense_id=None, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSES_MANAGE)
    task = _expense_task(project, task_id)
    if expense_id is None:
        row = PulseExpenseEntry(task=task, recorded_by=actor)
    else:
        row = get_object_or_404(PulseExpenseEntry.objects.select_for_update().filter(
            task=task), pk=expense_id)
        if row.voided_at:
            raise ValidationError("Voided expenses cannot be modified. Record a correction as a new entry.")
        if row.approval_status not in (row.ApprovalStatus.DRAFT, row.ApprovalStatus.REJECTED):
            raise ValidationError("Only draft or rejected expenses can be edited.")
        row.updated_by = actor
    previous = _snapshot(row) if row.pk else {}
    # Never trust a possibly stale ModelForm/model instance supplied by the caller.
    # Lock and re-read the category from the database before checking its archive
    # state. Otherwise a category archived earlier in this request/session could
    # still be used for a new expense by passing an older in-memory instance.
    selected_category = data.get("expense_category")
    category_pk = getattr(selected_category, "pk", selected_category)
    category = (PulseExpenseCategory.objects.select_for_update()
                .filter(pk=category_pk, project=project).first()) if category_pk else None
    if category is None:
        raise ValidationError({"expense_category": "Choose an expense category belonging to this project."})
    if category.archived_at and (not row.pk or category.pk != row.expense_category_id):
        raise ValidationError({"expense_category": "Choose an active expense category."})
    for key in ("description", "amount", "expense_date", "supplier_name", "reference", "notes"):
        if key in data:
            setattr(row, key, data[key])
    row.expense_category = category
    if expense_id and row.approval_status == row.ApprovalStatus.REJECTED:
        row.approval_status = row.ApprovalStatus.DRAFT
        row.review_note = ""
        row.reviewed_at = None
        row.reviewed_by = None
        row.submitted_at = None
    row.save()
    PulseExpenseChange.objects.create(
        entry=row, action="updated" if expense_id else "created",
        before=previous, after=_snapshot(row), changed_by=actor,
    )
    _audit(project, actor, "pulse.expense.updated" if expense_id else "pulse.expense.recorded",
           row, request, task_id=task.pk, expense_category_id=category.pk)
    return row


@transaction.atomic
def void_expense(*, actor, project_id, task_id, expense_id, reason, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSES_MANAGE)
    task = _expense_task(project, task_id)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    if row.voided_at:
        raise ValidationError("Expense already voided.")
    reason = " ".join((reason or "").split())
    if not reason or len(reason) > 240:
        raise ValidationError("A short reason (maximum 240 characters) is required to void an expense.")
    if row.approval_status == row.ApprovalStatus.APPROVED:
        if not membership_has_permission(actor, AccessPermission.PULSE_EXPENSES_APPROVE):
            raise PermissionDenied("Voiding an approved expense requires expense approval permission.")
        if row.payments.filter(voided_at__isnull=True).exists():
            raise ValidationError("Void/reverse its payment records before voiding an approved expense.")
    previous = _snapshot(row)
    row.voided_at = timezone.now()
    row.voided_by = actor
    row.void_reason = reason
    row.save()
    PulseExpenseChange.objects.create(entry=row, action="voided", before=previous,
                                      after=_snapshot(row), changed_by=actor)
    _audit(project, actor, "pulse.expense.voided", row, request, task_id=task.pk)
    return row


def expense_rollups(project):
    """Both submitted/recorded and approved SAR costs; use approved_* for budget reporting.

    The legacy `total`/`by_*` are non-voided recorded amounts for U05 compatibility.
    Finance screens must explicitly differentiate them from approved expense amounts.
    Never expose these results outside finance permissions.
    """
    rows = PulseExpenseEntry.objects.filter(task__category__project=project, voided_at__isnull=True)
    total = rows.aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00")
    by_task = {r["task_id"]: r["amount"] for r in rows.values("task_id").annotate(amount=Sum("amount"))}
    by_work_category = {r["task__category_id"]: r["amount"] for r in rows.values("task__category_id").annotate(amount=Sum("amount"))}
    by_expense_category = list(rows.values("expense_category_id", "expense_category__name")
                               .annotate(amount=Sum("amount")).order_by("expense_category__name"))
    approved = rows.filter(approval_status=PulseExpenseEntry.ApprovalStatus.APPROVED)
    pending = rows.filter(approval_status=PulseExpenseEntry.ApprovalStatus.PENDING)
    paid = PulseExpensePayment.objects.filter(entry__task__category__project=project, voided_at__isnull=True,
                                             entry__voided_at__isnull=True,
                                             entry__approval_status=PulseExpenseEntry.ApprovalStatus.APPROVED)
    return {
        "total": total, "by_task": by_task, "by_work_category": by_work_category,
        "by_expense_category": by_expense_category,
        "approved_total": approved.aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00"),
        "approved_by_task": {r["task_id"]: r["amount"] for r in approved.values("task_id").annotate(amount=Sum("amount"))},
        "approved_by_work_category": {r["task__category_id"]: r["amount"] for r in approved.values("task__category_id").annotate(amount=Sum("amount"))},
        "approved_by_expense_category": list(approved.values("expense_category_id", "expense_category__name")
            .annotate(amount=Sum("amount")).order_by("expense_category__name")),
        "pending_total": pending.aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00"),
        "paid_total": paid.aggregate(amount=Sum("amount"))["amount"] or Decimal("0.00"),
    }


@transaction.atomic
def submit_expense(*, actor, project_id, task_id, expense_id, request=None):
    """The recorder submits a draft; pending entries cannot be changed silently."""
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSES_MANAGE)
    task = _expense_task(project, task_id)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    if row.voided_at or row.approval_status != row.ApprovalStatus.DRAFT:
        raise ValidationError("Only non-voided draft expenses can be submitted.")
    before = _snapshot(row)
    row.approval_status = row.ApprovalStatus.PENDING
    row.submitted_at = timezone.now()
    row.save()
    PulseExpenseChange.objects.create(entry=row, action="submitted", before=before,
                                      after=_snapshot(row), changed_by=actor)
    _audit(project, actor, "pulse.expense.submitted", row, request)
    return row


@transaction.atomic
def review_expense(*, actor, project_id, task_id, expense_id, approve, note="", request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSES_APPROVE)
    task = _expense_task(project, task_id, editable=False)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    if row.voided_at or row.approval_status != row.ApprovalStatus.PENDING:
        raise ValidationError("Only non-voided pending expenses can be reviewed.")
    if actor.pk == row.recorded_by_id and actor.role != AccessRole.OWNER:
        raise PermissionDenied("The expense recorder cannot approve or reject their own expense.")
    note = (note or "").strip()
    if len(note) > 500 or (not approve and not note):
        raise ValidationError("Rejections require a reason; notes may not exceed 500 characters.")
    before = _snapshot(row)
    row.approval_status = row.ApprovalStatus.APPROVED if approve else row.ApprovalStatus.REJECTED
    row.reviewed_by = actor
    row.reviewed_at = timezone.now()
    row.review_note = note
    row.save()
    action = "approved" if approve else "rejected"
    PulseExpenseChange.objects.create(entry=row, action=action, before=before,
                                      after=_snapshot(row), changed_by=actor)
    _audit(project, actor, f"pulse.expense.{action}", row, request)
    return row


def _payment_amount(value):
    try:
        number = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError):
        raise ValidationError("Payment amount must be a valid amount in SAR.")
    if not number.is_finite() or number <= 0 or number.as_tuple().exponent < -2 or number >= Decimal("1000000000000"):
        raise ValidationError("Enter a positive payment amount with no more than two decimal places.")
    return number


@transaction.atomic
def record_expense_payment(*, actor, project_id, task_id, expense_id, data, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE, writable=False)
    if project.archived_at or project.status == Project.Status.ARCHIVED:
        raise ValidationError("Payments cannot be changed for archived projects.")
    task = _expense_task(project, task_id, editable=False)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    if row.voided_at or row.approval_status != row.ApprovalStatus.APPROVED:
        raise ValidationError("Only approved, non-voided expenses may have payments.")
    amount = _payment_amount(data.get("amount"))
    paid = row.payments.filter(voided_at__isnull=True).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    if amount + paid > row.amount:
        raise ValidationError("Payment would exceed the approved expense amount.")
    payment = PulseExpensePayment(entry=row, recorded_by=actor, amount=amount,
                                  paid_on=data.get("paid_on") or timezone.localdate(),
                                  method=data.get("method") or PulseExpensePayment.Method.BANK,
                                  reference=data.get("reference") or "", remarks=data.get("remarks") or "")
    payment.save()
    _audit(project, actor, "pulse.expense.payment_recorded", payment, request, expense_id=row.pk)
    return payment


@transaction.atomic
def void_expense_payment(*, actor, project_id, task_id, expense_id, payment_id, reason, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE, writable=False)
    if project.archived_at or project.status == Project.Status.ARCHIVED:
        raise ValidationError("Payments cannot be changed for archived projects.")
    task = _expense_task(project, task_id, editable=False)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    payment = get_object_or_404(PulseExpensePayment.objects.select_for_update(), pk=payment_id, entry=row)
    if payment.voided_at:
        raise ValidationError("Payment is already voided.")
    reason = " ".join((reason or "").split())
    if not reason or len(reason) > 240:
        raise ValidationError("A reason (maximum 240 characters) is required to void a payment.")
    payment.voided_at = timezone.now()
    payment.voided_by = actor
    payment.void_reason = reason
    payment.save()
    _audit(project, actor, "pulse.expense.payment_voided", payment, request, expense_id=row.pk)
    return payment


@transaction.atomic
def upload_expense_attachment(*, actor, project_id, task_id, expense_id, upload, request=None):
    project = _project(actor, project_id, AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE)
    task = _expense_task(project, task_id, editable=False)
    row = get_object_or_404(PulseExpenseEntry.objects.select_for_update(), pk=expense_id, task=task)
    if row.voided_at:
        raise ValidationError("Voided expenses cannot receive attachments.")
    validate_expense_evidence(upload)
    original = Path(upload.name).name[:240]
    attachment = PulseExpenseAttachment(entry=row, file=upload, original_name=original,
                                        size_bytes=upload.size, uploaded_by=actor)
    attachment.save()
    _audit(project, actor, "pulse.expense.attachment_uploaded", attachment, request, expense_id=row.pk)
    return attachment
