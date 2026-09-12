from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.models import CompanyOwnedModel


class BranchKind(models.TextChoices):
    BRANCH = "branch", "Branch"
    OFFICE = "office", "Office"


class EmploymentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ON_LEAVE = "on_leave", "On Leave"
    INACTIVE = "inactive", "Inactive"
    TERMINATED = "terminated", "Terminated"


class Branch(CompanyOwnedModel):
    """Company office/branch used only by the internal employee domain."""

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=160)
    location = models.CharField(max_length=160, blank=True)
    address = models.TextField(blank=True)
    manager_name = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=20, choices=BranchKind.choices, default=BranchKind.BRANCH, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_reason = models.CharField(max_length=300, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purge_after = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_reason = models.CharField(max_length=500, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="internal_branches_deleted",
    )

    class Meta:
        db_table = "internal_branch"
        ordering = ("code", "name")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="internal_branch_company_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="internal_branch_company_name_uniq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "name"), name="int_branch_company_active_idx"),
            models.Index(fields=("company", "archived_at", "name"), name="int_branch_company_archive_idx"),
            models.Index(fields=("company", "deleted_at", "name"), name="int_branch_trash_idx"),
        ]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.location = self.location.strip()
        self.address = self.address.strip()
        self.manager_name = self.manager_name.strip()
        self.archived_reason = self.archived_reason.strip()
        if not self.code:
            raise ValidationError({"code": "Branch code is required."})
        if not self.name:
            raise ValidationError({"name": "Branch name is required."})
        if self.archived_at and self.is_active:
            raise ValidationError({"is_active": "An archived branch or office cannot be active."})

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class Department(CompanyOwnedModel):
    """Reusable internal-company department master."""

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_reason = models.CharField(max_length=300, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purge_after = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_reason = models.CharField(max_length=500, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="internal_departments_deleted",
    )

    class Meta:
        db_table = "internal_department"
        ordering = ("code", "name")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="internal_department_company_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="internal_department_company_name_uniq"),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "name"), name="int_dept_company_active_idx"),
            models.Index(fields=("company", "archived_at", "name"), name="int_dept_company_archive_idx"),
            models.Index(fields=("company", "deleted_at", "name"), name="int_dept_trash_idx"),
        ]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        self.archived_reason = self.archived_reason.strip()
        if not self.code:
            raise ValidationError({"code": "Department code is required."})
        if not self.name:
            raise ValidationError({"name": "Department name is required."})
        if self.archived_at and self.is_active:
            raise ValidationError({"is_active": "An archived department cannot be active."})

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class InternalEmployee(CompanyOwnedModel):
    """Permanent master record for a company's own employee.

    Salary, attendance, bank/WPS and payroll data deliberately live in their owning models and
    are introduced by later domain upgrades.
    """

    employee_number = models.CharField(max_length=40)
    full_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=300, blank=True)
    joining_date = models.DateField()
    employment_end_date = models.DateField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True, db_index=True)
    archived_reason = models.CharField(max_length=300, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    purge_after = models.DateTimeField(null=True, blank=True, db_index=True)
    deletion_reason = models.CharField(max_length=500, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="internal_employees_deleted",
    )
    status = models.CharField(
        max_length=20,
        choices=EmploymentStatus.choices,
        default=EmploymentStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        db_table = "internal_employee"
        ordering = ("employee_number", "full_name")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "employee_number"),
                name="internal_employee_company_number_uniq",
            ),
            models.UniqueConstraint(
                fields=("company", "national_id"),
                condition=~Q(national_id=""),
                name="internal_employee_company_national_id_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in EmploymentStatus.choices]),
                name="internal_employee_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=models.F("joining_date")),
                name="internal_employee_end_after_join",
            ),
            models.CheckConstraint(
                condition=~Q(status=EmploymentStatus.TERMINATED) | Q(employment_end_date__isnull=False),
                name="internal_employee_terminated_has_end",
            ),
            models.CheckConstraint(
                condition=Q(archived_at__isnull=True) | Q(status__in=[EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED]),
                name="internal_employee_archive_requires_stopped_status",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "full_name"), name="int_emp_company_status_idx"),
            models.Index(fields=("company", "joining_date"), name="int_emp_company_join_idx"),
            models.Index(fields=("company", "deleted_at", "full_name"), name="int_emp_trash_idx"),
        ]

    def clean(self) -> None:
        self.employee_number = self.employee_number.strip().upper()
        self.full_name = self.full_name.strip()
        self.national_id = self.national_id.strip()
        self.phone = self.phone.strip()
        self.address = self.address.strip()
        self.archived_reason = self.archived_reason.strip()
        if not self.employee_number:
            raise ValidationError({"employee_number": "Employee number is required."})
        if not self.full_name:
            raise ValidationError({"full_name": "Employee name is required."})
        if self.employment_end_date and self.employment_end_date < self.joining_date:
            raise ValidationError({"employment_end_date": "Employment end date cannot be before the joining date."})
        if self.status == EmploymentStatus.TERMINATED and not self.employment_end_date:
            raise ValidationError({"employment_end_date": "Employment end date is required for a terminated employee."})
        if self.archived_at and self.status not in {EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED}:
            raise ValidationError({"status": "Only inactive or terminated employees can be archived."})

    def __str__(self) -> str:
        return f"{self.employee_number} · {self.full_name}"


class EmployeeOrganizationAssignment(CompanyOwnedModel):
    """Effective-dated branch, department and position history for an internal employee."""

    employee = models.ForeignKey(
        InternalEmployee,
        on_delete=models.PROTECT,
        related_name="organization_assignments",
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="employee_assignments",
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="employee_assignments",
    )
    position = models.CharField(max_length=160)
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "internal_employee_org_assignment"
        ordering = ("-effective_from", "-created_at")
        constraints = [
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="internal_emp_org_valid_date_range",
            ),
            models.UniqueConstraint(
                fields=("employee",),
                condition=Q(effective_to__isnull=True),
                name="internal_emp_org_one_open_assignment",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "employee", "-effective_from"), name="int_org_company_emp_date_idx"),
            models.Index(fields=("company", "branch", "effective_from"), name="int_org_company_branch_idx"),
            models.Index(fields=("company", "department", "effective_from"), name="int_org_company_dept_idx"),
        ]

    def clean(self) -> None:
        self.position = self.position.strip()
        self.reason = self.reason.strip()
        if not self.position:
            raise ValidationError({"position": "Position/designation is required."})
        if self.employee_id and self.company_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.branch_id and self.company_id and self.branch.company_id != self.company_id:
            raise ValidationError({"branch": "Branch must belong to the same company."})
        if self.department_id and self.company_id and self.department.company_id != self.company_id:
            raise ValidationError({"department": "Department must belong to the same company."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Assignment end date cannot be before its start date."})

    def __str__(self) -> str:
        return f"{self.employee} · {self.branch} · {self.department}"
