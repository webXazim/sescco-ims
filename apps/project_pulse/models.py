"""Project Pulse operational team; projects remain mastered by apps.projects.Project."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission


class PulseProjectTeamMember(models.Model):
    """One membership per project; role and active state retain audit/history continuity.

    A team role never grants application permission by itself. The related
    CompanyMembership's AccessProfile and project scope remain authoritative.
    """

    class Role(models.TextChoices):
        MANAGER = "manager", "Project manager"
        MEMBER = "member", "Team member"

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="pulse_team_members"
    )
    membership = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.PROTECT, related_name="pulse_project_assignments"
    )
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.MEMBER)
    is_active = models.BooleanField(default=True, db_index=True)
    assigned_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(blank=True, null=True)
    assigned_by = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="pulse_team_changes_made",
    )

    class Meta:
        ordering = ("project__code", "role", "membership__user__username")
        constraints = [
            models.UniqueConstraint(
                fields=("project", "membership"), name="pulse_project_membership_unique"
            ),
            models.UniqueConstraint(
                fields=("project",), condition=Q(role="manager", is_active=True),
                name="pulse_single_active_manager",
            ),
        ]
        indexes = [
            models.Index(fields=("project", "is_active", "role"), name="pulse_team_project_role_idx"),
        ]

    @property
    def has_project_access(self):
        """Roster display reflects subsequent access-profile/scope revocations."""
        if not self.is_active or not self.membership.is_active or not self.membership.user.is_active:
            return False
        return all(membership_has_permission(self.membership, perm) for perm in (
            AccessPermission.PULSE_OVERVIEW_VIEW, AccessPermission.PULSE_PROJECTS_VIEW,
        )) and membership_allows_project(self.membership, self.project)

    def clean(self):
        super().clean()
        errors = {}
        if self.project_id and self.membership_id:
            if self.project.company_id != self.membership.company_id:
                errors["membership"] = "The user must belong to the project's company."
            elif self.is_active:
                if self.project.deleted_at is not None or self.project.status == self.project.Status.ARCHIVED:
                    errors["project"] = "Team membership cannot be changed for an archived/deleted project."
                elif not self.membership.is_active or not self.membership.user.is_active:
                    errors["membership"] = "The user must have an active company membership."
                elif not all(membership_has_permission(self.membership, permission) for permission in (
                    AccessPermission.PULSE_OVERVIEW_VIEW,
                    AccessPermission.PULSE_PROJECTS_VIEW,
                )):
                    errors["membership"] = "Grant Project Pulse project access before assigning this user."
                elif not membership_allows_project(self.membership, self.project):
                    errors["membership"] = "The project is outside this user's authorized project scope."
        if self.assigned_by_id and self.project_id and self.assigned_by.company_id != self.project.company_id:
            errors["assigned_by"] = "The assigning user must belong to the project's company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.code}: {self.membership.user.display_name} ({self.role})"


class PulseWorkCategory(models.Model):
    """Project-specific operational work stream; finance fields come later.

    Archive is reversible. Never delete a category with historical tasks/expenses.
    """

    project = models.ForeignKey(
        "projects.Project", on_delete=models.PROTECT, related_name="pulse_work_categories"
    )
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=120, allow_unicode=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    progress_weight = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"), help_text="Relative contribution to project completion (not a financial value).")
    archived_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_by = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pulse_categories_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("project", "code"), name="pulse_cat_project_code_uniq"
            ),
            models.CheckConstraint(condition=Q(progress_weight__gt=0), name="pulse_category_weight_gt_zero"),
        ]
        indexes = [models.Index(fields=("project", "archived_at"), name="pulse_cat_project_archive_idx")]

    def clean(self):
        super().clean()
        from django.utils.text import slugify
        errors = {}
        self.name = " ".join((self.name or "").split())
        if not self.name:
            errors["name"] = "Category name is required."
        self.code = slugify(self.name, allow_unicode=True)[:120]
        if not self.code:
            errors["name"] = "Use letters or numbers in the category name."
        if self.progress_weight is not None and self.progress_weight <= 0:
            errors["progress_weight"] = "Category progress weight must be greater than zero."
        if self.project_id and self.created_by_id and self.project.company_id != self.created_by.company_id:
            errors["created_by"] = "Category creator must belong to the project company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.project.code} · {self.name}"


class PulseTask(models.Model):
    """One task in one work category with weighted operational completion."""

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Not started"
        IN_PROGRESS = "in_progress", "In progress"
        BLOCKED = "blocked", "Blocked"
        ON_HOLD = "on_hold", "On hold"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    category = models.ForeignKey(
        PulseWorkCategory, on_delete=models.PROTECT, related_name="tasks"
    )
    title = models.CharField(max_length=180)
    description = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.PROTECT, null=True, blank=True,
        related_name="pulse_assigned_tasks",
    )
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.NORMAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    planned_start = models.DateField(blank=True, null=True)
    due_date = models.DateField(blank=True, null=True, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    progress_weight = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("1.00"), help_text="Relative contribution within its work category (not a financial value).")
    archived_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_by = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="pulse_tasks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "due_date", "pk")
        constraints = [
            models.CheckConstraint(condition=Q(progress_weight__gt=0), name="pulse_task_weight_gt_zero"),
            models.CheckConstraint(condition=Q(progress_percent__gte=0, progress_percent__lte=100), name="pulse_task_percent_range"),
            models.CheckConstraint(
                condition=(Q(status="completed", progress_percent=100) |
                           (~Q(status="completed") & Q(progress_percent__lt=100))),
                name="pulse_task_complete_percent_consistent",
            ),
            models.CheckConstraint(condition=~Q(status="not_started") | Q(progress_percent=0), name="pulse_task_not_started_zero"),
        ]
        indexes = [
            models.Index(fields=("category", "archived_at", "status"), name="pulse_task_cat_state_idx"),
            models.Index(fields=("assigned_to", "archived_at", "due_date"), name="pulse_task_assignee_due_idx"),
        ]

    @property
    def project(self):
        return self.category.project

    def clean(self):
        super().clean()
        errors = {}
        self.title = " ".join((self.title or "").split())
        if not self.title:
            errors["title"] = "Task title is required."
        if self.progress_weight is not None and self.progress_weight <= 0:
            errors["progress_weight"] = "Task progress weight must be greater than zero."
        if self.progress_percent is not None and not (0 <= self.progress_percent <= 100):
            errors["progress_percent"] = "Progress must be between 0 and 100."
        elif self.status == self.Status.COMPLETED and self.progress_percent != 100:
            errors["progress_percent"] = "Completed tasks must have 100% progress."
        elif self.status != self.Status.COMPLETED and self.progress_percent == 100:
            errors["status"] = "A task at 100% must be completed."
        elif self.status == self.Status.NOT_STARTED and self.progress_percent != 0:
            errors["status"] = "Not-started tasks must have 0% progress."
        if self.planned_start and self.due_date and self.due_date < self.planned_start:
            errors["due_date"] = "Due date cannot be earlier than the planned start."
        if self.category_id:
            if self.category.archived_at is not None and self.archived_at is None:
                errors["category"] = "Cannot place an active task under an archived category."
            if self.created_by_id and self.created_by.company_id != self.category.project.company_id:
                errors["created_by"] = "Creator must belong to the project company."
            if self.assigned_to_id and self.archived_at is None:
                # Existing assignee may have left the project after assignment. Do
                # not block unrelated progress/status edits by authorized managers;
                # do revalidate on reassignment, moving category or restore.
                persisted = (PulseTask.objects.filter(pk=self.pk).values(
                    "assigned_to_id", "category_id", "archived_at"
                ).first() if self.pk else None)
                stable_existing = (persisted and persisted["assigned_to_id"] == self.assigned_to_id
                    and persisted["category_id"] == self.category_id
                    and persisted["archived_at"] is None)
                if not stable_existing:
                    assignment = PulseProjectTeamMember.objects.filter(
                    project_id=self.category.project_id, membership_id=self.assigned_to_id, is_active=True,
                    ).select_related("membership__user", "membership__access_profile", "project").first()
                    if not assignment or not assignment.has_project_access or not membership_has_permission(
                        assignment.membership, AccessPermission.PULSE_TASKS_VIEW
                    ):
                        errors["assigned_to"] = "Choose an active team member with Project Pulse task access."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.category.project.code} · {self.title}"


class PulseProgressUpdate(models.Model):
    """Append-only progress history; service controls writes, with audited actor."""

    task = models.ForeignKey(PulseTask, on_delete=models.PROTECT, related_name="progress_updates")
    previous_percent = models.PositiveSmallIntegerField()
    new_percent = models.PositiveSmallIntegerField()
    previous_status = models.CharField(max_length=20, choices=PulseTask.Status.choices)
    new_status = models.CharField(max_length=20, choices=PulseTask.Status.choices)
    note = models.TextField(blank=True)
    updated_by = models.ForeignKey(
        "accounts.CompanyMembership", on_delete=models.PROTECT, related_name="pulse_progress_updates"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("task", "-created_at"), name="pulse_progress_task_date_idx")]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Progress history is append-only.")
        return super().save(*args, **kwargs)



class PulseExpenseCategory(models.Model):
    """Reusable per-project expense classification, distinct from work categories.

    Categories cannot be deleted once referenced. Old expenses retain their category
    even when the category is archived for future entry.
    """
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="pulse_expense_categories")
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=120, allow_unicode=True, blank=True)
    description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name="pulse_expense_categories_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "pk")
        constraints = [models.UniqueConstraint(fields=("project", "code"), name="pulse_exp_cat_proj_code_uniq")]
        indexes = [models.Index(fields=("project", "archived_at"), name="pulse_exp_cat_proj_active_idx")]

    def clean(self):
        super().clean()
        from django.utils.text import slugify
        errors = {}
        self.name = " ".join((self.name or "").split())
        if not self.name:
            errors["name"] = "Expense category name is required."
        self.code = slugify(self.name, allow_unicode=True)[:120]
        if not self.code:
            errors["name"] = "Use letters or numbers in the category name."
        if self.project_id and self.created_by_id and self.project.company_id != self.created_by.company_id:
            errors["created_by"] = "Expense category creator must belong to this project company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class PulseExpenseEntry(models.Model):
    """Standalone task cost; approval and payment records are separate."""
    class ApprovalStatus(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
    task = models.ForeignKey(PulseTask, on_delete=models.PROTECT, related_name="expense_entries")
    expense_category = models.ForeignKey(PulseExpenseCategory, on_delete=models.PROTECT,
                                         related_name="expense_entries")
    description = models.CharField(max_length=240)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    supplier_name = models.CharField(max_length=160, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    approval_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT, db_index=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT,
                                    blank=True, null=True, related_name="pulse_expenses_reviewed")
    review_note = models.CharField(max_length=500, blank=True)
    recorded_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT,
                                    related_name="pulse_expenses_recorded")
    updated_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.SET_NULL,
                                   blank=True, null=True, related_name="pulse_expenses_edited")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    voided_at = models.DateTimeField(null=True, blank=True, db_index=True)
    voided_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.SET_NULL,
                                  blank=True, null=True, related_name="pulse_expenses_voided")
    void_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ("-expense_date", "-pk")
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="pulse_expense_amount_gt_zero")]
        indexes = [
            models.Index(fields=("task", "voided_at"), name="pulse_exp_task_void_idx"),
            models.Index(fields=("expense_category", "expense_date"), name="pulse_exp_cat_date_idx"),
            models.Index(fields=("approval_status", "voided_at"), name="pulse_exp_approval_idx"),
        ]

    @property
    def project(self):
        return self.task.category.project

    def clean(self):
        super().clean()
        errors = {}
        self.description = " ".join((self.description or "").split())
        if not self.description:
            errors["description"] = "Expense description is required."
        if self.amount is None or self.amount <= 0:
            errors["amount"] = "Amount must be greater than zero."
        if self.task_id and self.expense_category_id:
            if self.task.category.project_id != self.expense_category.project_id:
                errors["expense_category"] = "Expense category belongs to a different project."
            elif self.pk is None and self.expense_category.archived_at is not None:
                errors["expense_category"] = "Archived expense categories cannot be used for new entries."
        if self.task_id and self.recorded_by_id and self.recorded_by.company_id != self.task.category.project.company_id:
            errors["recorded_by"] = "Expense recorder must belong to this project company."
        if self.task_id and self.updated_by_id and self.updated_by.company_id != self.task.category.project.company_id:
            errors["updated_by"] = "Expense editor must belong to this project company."
        if self.task_id and self.reviewed_by_id and self.reviewed_by.company_id != self.task.category.project.company_id:
            errors["reviewed_by"] = "Expense reviewer must belong to this project company."
        if self.task_id and self.voided_by_id and self.voided_by.company_id != self.task.category.project.company_id:
            errors["voided_by"] = "Expense voider must belong to this project company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.task.title} · {self.description}"


class PulseExpenseChange(models.Model):
    """Append-only financial change snapshots; visible only inside expense views.

    General platform audit events deliberately do not replicate financial values.
    """
    class Action(models.TextChoices):
        CREATED = "created", "Recorded"
        UPDATED = "updated", "Edited"
        VOIDED = "voided", "Voided"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    entry = models.ForeignKey(PulseExpenseEntry, on_delete=models.PROTECT, related_name="changes")
    action = models.CharField(max_length=12, choices=Action.choices)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    changed_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT,
                                   related_name="pulse_expense_changes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("entry", "-created_at"), name="pulse_exp_change_date_idx")]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Expense change history is append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Expense change history cannot be deleted.")


class PulseExpensePayment(models.Model):
    """Immutable payment amounts; void/reversal records retain financial history."""
    class Method(models.TextChoices):
        BANK = "bank", "Bank transfer"
        CASH = "cash", "Cash"
        CHEQUE = "cheque", "Cheque"
        OTHER = "other", "Other"

    entry = models.ForeignKey(PulseExpenseEntry, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_on = models.DateField(default=timezone.localdate)
    method = models.CharField(max_length=12, choices=Method.choices, default=Method.BANK)
    reference = models.CharField(max_length=120, blank=True)
    remarks = models.TextField(blank=True)
    recorded_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, related_name="pulse_payments_recorded")
    created_at = models.DateTimeField(auto_now_add=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, null=True, blank=True, related_name="pulse_payments_voided")
    void_reason = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ("-paid_on", "-pk")
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="pulse_payment_amount_positive")]
        indexes = [models.Index(fields=("entry", "voided_at"), name="pulse_payment_entry_void_idx")]

    def clean(self):
        super().clean()
        errors = {}
        if self.entry_id and self.recorded_by_id and self.entry.project.company_id != self.recorded_by.company_id:
            errors["recorded_by"] = "Payment recorder must belong to the project company."
        if self.entry_id and self.voided_by_id and self.entry.project.company_id != self.voided_by.company_id:
            errors["voided_by"] = "Payment voider must belong to the project company."
        if self.amount is None or self.amount <= 0:
            errors["amount"] = "Payment amount must be greater than zero."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ("entry_id", "amount", "paid_on", "method", "reference", "remarks", "recorded_by_id", "created_at")
            if any(getattr(self, key) != getattr(previous, key) for key in immutable):
                raise ValidationError("Payment details are immutable; void a payment and enter a correction.")
            if previous.voided_at and self.voided_at != previous.voided_at:
                raise ValidationError("A voided payment cannot be restored.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Payments cannot be deleted; void instead.")


from .private_storage import PulsePrivateStorage, expense_upload_name


class PulseExpenseAttachment(models.Model):
    """Private receipts/evidence. Always retrieve through scoped authorized view."""
    entry = models.ForeignKey(PulseExpenseEntry, on_delete=models.PROTECT, related_name="attachments")
    file = models.FileField(storage=PulsePrivateStorage(), upload_to=expense_upload_name, max_length=300)
    original_name = models.CharField(max_length=240)
    size_bytes = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, related_name="pulse_expense_uploads")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-uploaded_at", "-pk")

    def clean(self):
        super().clean()
        if self.entry_id and self.uploaded_by_id and self.entry.project.company_id != self.uploaded_by.company_id:
            raise ValidationError({"uploaded_by": "Uploader must belong to the project company."})

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Receipt attachments are append-only.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Receipt attachments are retained for audit history.")


class PulseBudgetRevision(models.Model):
    """Versioned, individually approved work-category cost budget in SAR.

    Submitted revisions are immutable except for one pending -> approved/rejected
    decision. Never edit historic approved amounts or delete audit evidence.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending approval"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    category = models.ForeignKey(PulseWorkCategory, on_delete=models.PROTECT, related_name="budget_revisions")
    revision_number = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    submitted_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, related_name="pulse_budgets_submitted")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, null=True, blank=True, related_name="pulse_budgets_reviewed")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ("-revision_number", "-pk")
        constraints = [
            models.UniqueConstraint(fields=("category", "revision_number"), name="pulse_budget_cat_rev_unique"),
            models.UniqueConstraint(fields=("category",), condition=Q(status="pending"), name="pulse_budget_one_pending"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="pulse_budget_amount_nonnegative"),
            models.CheckConstraint(condition=Q(revision_number__gt=0), name="pulse_budget_rev_positive"),
        ]
        indexes = [models.Index(fields=("category", "status", "-revision_number"), name="pulse_budget_cat_status_idx")]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is None or self.amount < 0:
            errors["amount"] = "Budget cannot be negative."
        if not self.reason or not self.reason.strip():
            errors["reason"] = "Explain the initial budget or the revision."
        if self.category_id:
            company_id = self.category.project.company_id
            for field in ("submitted_by", "reviewed_by"):
                member = getattr(self, field, None)
                if member is not None and member.company_id != company_id:
                    errors[field] = "The user must belong to the project company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            immutable = ("category_id", "revision_number", "amount", "reason", "submitted_by_id", "submitted_at")
            if any(getattr(old, field) != getattr(self, field) for field in immutable):
                raise ValidationError("Budget amounts and revision history are immutable. Submit a new revision.")
            if old.status != self.Status.PENDING or self.status not in (self.Status.APPROVED, self.Status.REJECTED):
                raise ValidationError("Only a pending budget revision may be reviewed once.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Budget revisions are retained for financial audit history.")


class PulseCommercialRecord(models.Model):
    """Common audited approval lifecycle for confidential project commercial figures.

    Abstract; only the service layer can authorize approvals. Do not delete or
    silently replace approved financial history.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    submitted_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey("accounts.CompanyMembership", on_delete=models.PROTECT,
                                    related_name="+", null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.CharField(max_length=500, blank=True)

    class Meta:
        abstract = True
        ordering = ("-submitted_at", "-pk")

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is None or not self.amount.is_finite():
            errors["amount"] = "Enter a valid SAR amount."
        if not (self.reason or "").strip():
            errors["reason"] = "A reason is required."
        if self.project_id:
            for field in ("submitted_by", "reviewed_by"):
                member = getattr(self, field, None)
                if member is not None and member.company_id != self.project.company_id:
                    errors[field] = "The reviewer or proposer belongs to another company."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.get(pk=self.pk)
            immutable = ("project_id", "amount", "reason", "submitted_by_id", "submitted_at")
            if any(getattr(previous, field) != getattr(self, field) for field in immutable):
                raise ValidationError("Commercial records are immutable; submit another proposal.")
            if previous.status != self.Status.PENDING or self.status not in (self.Status.APPROVED, self.Status.REJECTED):
                raise ValidationError("Only a pending commercial record may be reviewed once.")
            if not self.reviewed_by_id or not self.reviewed_at:
                raise ValidationError("A financial decision requires a reviewer and date.")
        else:
            if self.status != self.Status.PENDING or self.reviewed_at or self.reviewed_by_id:
                raise ValidationError("New commercial submissions must start pending.")
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Commercial history cannot be deleted.")


class PulseContractRevision(PulseCommercialRecord):
    """Approved FULL contract value, not an incremental amount; before variations."""
    class Meta(PulseCommercialRecord.Meta):
        constraints = [
            models.UniqueConstraint(fields=("project",), condition=Q(status="pending"), name="pulse_contract_one_pending"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="pulse_contract_nonnegative"),
        ]

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < 0:
            raise ValidationError({"amount": "Contract value cannot be negative."})


class PulseContractVariation(PulseCommercialRecord):
    """Approved signed change orders; negative values represent reductions."""
    description = models.CharField(max_length=220)
    reference = models.CharField(max_length=100, blank=True)

    class Meta(PulseCommercialRecord.Meta):
        constraints = [models.CheckConstraint(condition=~Q(amount=0), name="pulse_variation_nonzero")]

    def clean(self):
        super().clean()
        if self.amount == 0:
            raise ValidationError({"amount": "Variation must be positive or negative, not zero."})
        if not (self.description or "").strip():
            raise ValidationError({"description": "Describe the contract variation."})

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.description != self.description or old.reference != self.reference:
                raise ValidationError("Approved variation descriptions cannot be edited.")
        return super().save(*args, **kwargs)


class PulseCostForecast(PulseCommercialRecord):
    """Approved estimate of REMAINING project costs, in SAR (not total cost).

    Forecast final cost = approved expenses to date + remaining-cost estimate.
    This is a forecast, not a financial income statement or earned profit.
    """
    as_of_date = models.DateField(default=timezone.localdate)
    actual_cost_basis = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True,
        help_text="Approved project expenses at the time this forecast was approved.")

    class Meta(PulseCommercialRecord.Meta):
        constraints = [
            models.UniqueConstraint(fields=("project",), condition=Q(status="pending"), name="pulse_forecast_one_pending"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="pulse_forecast_nonnegative"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.amount is not None and self.amount < 0:
            errors["amount"] = "Remaining cost cannot be negative."
        if self.status == self.Status.PENDING and self.actual_cost_basis is not None:
            errors["actual_cost_basis"] = "Pending forecasts cannot have an approved-cost baseline."
        if self.status == self.Status.APPROVED and self.actual_cost_basis is None:
            errors["actual_cost_basis"] = "Approval requires a snapshot of approved actual expenses."
        if self.actual_cost_basis is not None and self.actual_cost_basis < 0:
            errors["actual_cost_basis"] = "The approved-cost baseline cannot be negative."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.get(pk=self.pk)
            if old.as_of_date != self.as_of_date or (old.actual_cost_basis is not None and old.actual_cost_basis != self.actual_cost_basis):
                raise ValidationError("Forecast baseline cannot be changed.")
        return super().save(*args, **kwargs)
