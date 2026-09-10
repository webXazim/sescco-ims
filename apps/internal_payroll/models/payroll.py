from __future__ import annotations

from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import hours_field, money_field
from apps.core.models import CompanyOwnedModel
from .salary import SalaryComponentCalculation, SalaryComponentCategory, SalaryComponentRecurrence, WPSMapping


def _model_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PayrollProrationMethod(models.TextChoices):
    NOT_CONFIGURED = "not_configured", "Not configured"
    CALENDAR_DAYS = "calendar_days", "Calendar days"
    NO_PRORATION = "no_proration", "No proration"


class InternalPayrollPolicy(CompanyOwnedModel):
    """Company-level payroll calculation rules that must be explicit before ambiguous cases calculate."""

    proration_method = models.CharField(
        max_length=24,
        choices=PayrollProrationMethod.choices,
        default=PayrollProrationMethod.NOT_CONFIGURED,
    )

    class Meta:
        db_table = "internal_payroll_policy"
        constraints = [
            models.UniqueConstraint(fields=("company",), name="int_pay_policy_company_uniq"),
            models.CheckConstraint(
                condition=Q(proration_method__in=[value for value, _label in PayrollProrationMethod.choices]),
                name="int_pay_policy_proration_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.company} · {self.get_proration_method_display()}"


class PayrollAdjustmentType(models.TextChoices):
    SALARY_ADVANCE = "salary_advance", "Salary Advance"
    ADVANCE_RECOVERY = "advance_recovery", "Advance Recovery"
    BONUS = "bonus", "Bonus"
    REIMBURSEMENT = "reimbursement", "Reimbursement"
    FINE = "fine", "Fine / Penalty"
    OTHER_EARNING = "other_earning", "Other Earning"
    OTHER_DEDUCTION = "other_deduction", "Other Deduction"


class PayrollAdjustmentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    REVIEW = "review", "Review"
    APPROVED = "approved", "Approved"


class PayrollAdjustment(CompanyOwnedModel):
    """One-time internal employee transaction kept outside the permanent salary structure."""

    employee = models.ForeignKey(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="payroll_adjustments",
    )
    transaction_date = models.DateField()
    period_start = models.DateField(db_index=True)
    adjustment_type = models.CharField(max_length=32, choices=PayrollAdjustmentType.choices)
    amount = money_field()
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    recovery_plan = models.CharField(max_length=200, blank=True)
    installment_amount = money_field(null=True, blank=True)
    recovery_start = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=16,
        choices=PayrollAdjustmentStatus.choices,
        default=PayrollAdjustmentStatus.DRAFT,
        db_index=True,
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_internal_payroll_adjustments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_internal_payroll_adjustments",
    )

    class Meta:
        db_table = "internal_payroll_adjustment"
        ordering = ("-transaction_date", "-created_at")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="int_pay_adj_amount_positive"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in PayrollAdjustmentStatus.choices]),
                name="int_pay_adj_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(adjustment_type__in=[value for value, _label in PayrollAdjustmentType.choices]),
                name="int_pay_adj_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(installment_amount__isnull=True) | Q(installment_amount__gt=0),
                name="int_pay_adj_installment_positive",
            ),
            models.CheckConstraint(
                condition=Q(installment_amount__isnull=True) | Q(installment_amount__lte=models.F("amount")),
                name="int_pay_adj_installment_lte_amount",
            ),
            models.CheckConstraint(
                condition=Q(recovery_start__isnull=True) | Q(recovery_start__gte=models.F("transaction_date")),
                name="int_pay_adj_recovery_after_txn",
            ),
            models.CheckConstraint(
                condition=Q(adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE)
                | (Q(recovery_start__isnull=True) & Q(installment_amount__isnull=True) & Q(recovery_plan="")),
                name="int_pay_adj_schedule_advance_only",
            ),
            models.UniqueConstraint(
                fields=("company", "reference"),
                condition=~Q(reference=""),
                name="int_pay_adj_company_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "period_start", "status"), name="int_pay_adj_period_status_idx"),
            models.Index(fields=("company", "employee", "period_start"), name="int_pay_adj_emp_period_idx"),
            models.Index(fields=("company", "employee", "adjustment_type", "status"), name="int_pay_adj_balance_idx"),
        ]

    def clean(self) -> None:
        self.reason = self.reason.strip()
        self.reference = self.reference.strip().upper()
        self.recovery_plan = self.recovery_plan.strip()
        if not self.reason:
            raise ValidationError({"reason": "A clear transaction reason is required."})
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Adjustment period must start on the first day of a month."})
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.amount is None or self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.installment_amount is not None and self.installment_amount <= Decimal("0"):
            raise ValidationError({"installment_amount": "Installment amount must be greater than zero."})
        if self.recovery_plan and self.adjustment_type != PayrollAdjustmentType.SALARY_ADVANCE:
            raise ValidationError({"recovery_plan": "Recovery scheduling is available only for Salary Advance transactions."})
        if self.recovery_start and self.adjustment_type != PayrollAdjustmentType.SALARY_ADVANCE:
            raise ValidationError({"recovery_start": "Recovery scheduling is available only for Salary Advance transactions."})
        if self.installment_amount and self.adjustment_type != PayrollAdjustmentType.SALARY_ADVANCE:
            raise ValidationError({"installment_amount": "Recovery scheduling is available only for Salary Advance transactions."})
        if self.installment_amount is not None and self.installment_amount > self.amount:
            raise ValidationError({"installment_amount": "Installment amount cannot exceed the salary advance amount."})
        if self.recovery_start and self.recovery_start < self.transaction_date:
            raise ValidationError({"recovery_start": "Recovery cannot start before the salary advance transaction date."})

    def __str__(self) -> str:
        return f"{self.employee} · {self.get_adjustment_type_display()} · {self.amount}"


class PayrollRunStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CALCULATED = "calculated", "Calculated"
    REVIEW = "review", "Review"
    APPROVED = "approved", "Approved"
    PAYMENT_PROCESSING = "payment_processing", "Payment Processing"
    PAID = "paid", "Paid"
    CLOSED = "closed", "Closed"


class PayrollRun(CompanyOwnedModel):
    """One internal-company payroll lifecycle per calendar month."""

    period_start = models.DateField()
    period_end = models.DateField()
    attendance_period = models.ForeignKey(
        "internal_payroll.AttendancePeriod",
        on_delete=models.PROTECT,
        related_name="payroll_runs",
        null=True,
        blank=True,
    )
    attendance_revision = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=24,
        choices=PayrollRunStatus.choices,
        default=PayrollRunStatus.DRAFT,
        db_index=True,
    )
    revision = models.PositiveIntegerField(default=0)
    calculation_version = models.PositiveSmallIntegerField(default=1)
    source_fingerprint = models.CharField(max_length=64, blank=True)
    snapshot_fingerprint = models.CharField(max_length=64, blank=True)

    employee_count = models.PositiveIntegerField(default=0)
    total_basic = money_field(default=Decimal("0"))
    total_allowances = money_field(default=Decimal("0"))
    total_overtime = money_field(default=Decimal("0"))
    total_other_earnings = money_field(default=Decimal("0"))
    total_gross = money_field(default=Decimal("0"))
    total_advance_recovery = money_field(default=Decimal("0"))
    total_other_deductions = money_field(default=Decimal("0"))
    total_deductions = money_field(default=Decimal("0"))
    total_net = money_field(default=Decimal("0"))

    calculated_at = models.DateTimeField(null=True, blank=True)
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calculated_internal_payroll_runs",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_internal_payroll_runs",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_internal_payroll_runs",
    )
    reviewer_note = models.TextField(blank=True)

    class Meta:
        db_table = "internal_payroll_run"
        ordering = ("-period_start",)
        constraints = [
            models.UniqueConstraint(fields=("company", "period_start"), name="int_pay_run_company_period_uniq"),
            models.CheckConstraint(condition=Q(period_end__gte=models.F("period_start")), name="int_pay_run_valid_range"),
            models.CheckConstraint(condition=Q(revision__gte=0), name="int_pay_run_revision_nonneg"),
            models.CheckConstraint(condition=Q(attendance_revision__gte=0), name="int_pay_run_att_rev_nonneg"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in PayrollRunStatus.choices]),
                name="int_pay_run_status_valid",
            ),
            models.CheckConstraint(condition=Q(total_basic__gte=0), name="int_pay_run_basic_nonneg"),
            models.CheckConstraint(condition=Q(total_allowances__gte=0), name="int_pay_run_allow_nonneg"),
            models.CheckConstraint(condition=Q(total_overtime__gte=0), name="int_pay_run_ot_nonneg"),
            models.CheckConstraint(condition=Q(total_other_earnings__gte=0), name="int_pay_run_other_earn_nonneg"),
            models.CheckConstraint(condition=Q(total_gross__gte=0), name="int_pay_run_gross_nonneg"),
            models.CheckConstraint(condition=Q(total_advance_recovery__gte=0), name="int_pay_run_adv_rec_nonneg"),
            models.CheckConstraint(condition=Q(total_other_deductions__gte=0), name="int_pay_run_other_ded_nonneg"),
            models.CheckConstraint(condition=Q(total_deductions__gte=0), name="int_pay_run_deductions_nonneg"),
            models.CheckConstraint(condition=Q(total_net__gte=0), name="int_pay_run_net_nonneg"),
            models.CheckConstraint(
                condition=Q(
                    total_gross=models.F("total_basic")
                    + models.F("total_allowances")
                    + models.F("total_overtime")
                    + models.F("total_other_earnings")
                ),
                name="int_pay_run_gross_math",
            ),
            models.CheckConstraint(
                condition=Q(total_deductions=models.F("total_advance_recovery") + models.F("total_other_deductions")),
                name="int_pay_run_ded_math",
            ),
            models.CheckConstraint(
                condition=Q(total_net=models.F("total_gross") - models.F("total_deductions")),
                name="int_pay_run_net_math",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "status", "-period_start"), name="int_pay_run_status_idx"),
        ]

    def clean(self) -> None:
        self.reviewer_note = self.reviewer_note.strip()
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Payroll period must start on the first day of a month."})
        expected_end = self.period_start.replace(day=monthrange(self.period_start.year, self.period_start.month)[1])
        if self.period_end != expected_end:
            raise ValidationError({"period_end": "Payroll period must end on the final day of the same month."})
        if self.company_id and self.attendance_period_id and self.attendance_period.company_id != self.company_id:
            raise ValidationError({"attendance_period": "Attendance period must belong to the same company."})
        if self.attendance_period_id and self.attendance_period.period_start != self.period_start:
            raise ValidationError({"attendance_period": "Attendance and payroll periods must match."})
        expected_gross = _model_money(self.total_basic + self.total_allowances + self.total_overtime + self.total_other_earnings)
        expected_deductions = _model_money(self.total_advance_recovery + self.total_other_deductions)
        expected_net = _model_money(self.total_gross - self.total_deductions)
        if self.total_gross != expected_gross:
            raise ValidationError({"total_gross": "Payroll gross total does not match its earning components."})
        if self.total_deductions != expected_deductions:
            raise ValidationError({"total_deductions": "Payroll deduction total does not match its deduction components."})
        if self.total_net != expected_net:
            raise ValidationError({"total_net": "Payroll net total must equal gross less deductions."})

    def __str__(self) -> str:
        return f"{self.company} · {self.period_start:%B %Y} · {self.get_status_display()}"


class PayrollRunLine(CompanyOwnedModel):
    """Immutable employee calculation snapshot once a payroll run moves into Review."""

    run = models.ForeignKey(PayrollRun, on_delete=models.PROTECT, related_name="lines")
    employee = models.ForeignKey(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="payroll_run_lines",
    )
    employee_number = models.CharField(max_length=40)
    employee_name = models.CharField(max_length=200)
    branch_id_snapshot = models.UUIDField(null=True, blank=True)
    branch_code = models.CharField(max_length=30, blank=True)
    branch_name = models.CharField(max_length=160, blank=True)
    department_id_snapshot = models.UUIDField(null=True, blank=True)
    department_code = models.CharField(max_length=30, blank=True)
    department_name = models.CharField(max_length=160, blank=True)
    position = models.CharField(max_length=160, blank=True)

    regular_hours = hours_field(default=Decimal("0"))
    absent_days = models.PositiveSmallIntegerField(default=0)
    leave_days = models.PositiveSmallIntegerField(default=0)
    sick_days = models.PositiveSmallIntegerField(default=0)
    holiday_days = models.PositiveSmallIntegerField(default=0)
    off_days = models.PositiveSmallIntegerField(default=0)
    overtime_hours = hours_field(default=Decimal("0"))
    overtime_amount = money_field(default=Decimal("0"))
    overtime_policy_code = models.CharField(max_length=30, blank=True)
    overtime_policy_name = models.CharField(max_length=160, blank=True)
    overtime_rate = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)

    basic = money_field(default=Decimal("0"))
    allowances = money_field(default=Decimal("0"))
    other_earnings = money_field(default=Decimal("0"))
    gross = money_field(default=Decimal("0"))
    advance_recovery = money_field(default=Decimal("0"))
    other_deductions = money_field(default=Decimal("0"))
    total_deductions = money_field(default=Decimal("0"))
    net = money_field(default=Decimal("0"))

    class Meta:
        db_table = "internal_payroll_run_line"
        ordering = ("employee_number", "employee_name")
        constraints = [
            models.UniqueConstraint(fields=("run", "employee"), name="int_pay_line_run_emp_uniq"),
            models.CheckConstraint(condition=Q(regular_hours__gte=0), name="int_pay_line_hours_nonneg"),
            models.CheckConstraint(condition=Q(overtime_hours__gte=0), name="int_pay_line_ot_hours_nonneg"),
            models.CheckConstraint(condition=Q(overtime_amount__gte=0), name="int_pay_line_ot_nonneg"),
            models.CheckConstraint(condition=Q(basic__gte=0), name="int_pay_line_basic_nonneg"),
            models.CheckConstraint(condition=Q(allowances__gte=0), name="int_pay_line_allow_nonneg"),
            models.CheckConstraint(condition=Q(other_earnings__gte=0), name="int_pay_line_other_earn_nonneg"),
            models.CheckConstraint(condition=Q(gross__gte=0), name="int_pay_line_gross_nonneg"),
            models.CheckConstraint(condition=Q(advance_recovery__gte=0), name="int_pay_line_adv_rec_nonneg"),
            models.CheckConstraint(condition=Q(other_deductions__gte=0), name="int_pay_line_other_ded_nonneg"),
            models.CheckConstraint(condition=Q(total_deductions__gte=0), name="int_pay_line_ded_nonneg"),
            models.CheckConstraint(condition=Q(net__gte=0), name="int_pay_line_net_nonneg"),
            models.CheckConstraint(
                condition=Q(gross=models.F("basic") + models.F("allowances") + models.F("overtime_amount") + models.F("other_earnings")),
                name="int_pay_line_gross_math",
            ),
            models.CheckConstraint(
                condition=Q(total_deductions=models.F("advance_recovery") + models.F("other_deductions")),
                name="int_pay_line_ded_math",
            ),
            models.CheckConstraint(
                condition=Q(net=models.F("gross") - models.F("total_deductions")),
                name="int_pay_line_net_math",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "run", "employee_number"), name="int_pay_line_run_emp_idx"),
            models.Index(fields=("company", "branch_id_snapshot"), name="int_pay_line_branch_idx"),
            models.Index(fields=("company", "department_id_snapshot"), name="int_pay_line_dept_idx"),
        ]

    def clean(self) -> None:
        self.employee_number = self.employee_number.strip().upper()
        self.employee_name = self.employee_name.strip()
        self.branch_code = self.branch_code.strip().upper()
        self.branch_name = self.branch_name.strip()
        self.department_code = self.department_code.strip().upper()
        self.department_name = self.department_name.strip()
        self.position = self.position.strip()
        self.overtime_policy_code = self.overtime_policy_code.strip().upper()
        self.overtime_policy_name = self.overtime_policy_name.strip()
        if self.company_id and self.run_id and self.run.company_id != self.company_id:
            raise ValidationError({"run": "Payroll run must belong to the same company."})
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.run_id and self.employee_id and self.run.period_end < self.employee.joining_date:
            raise ValidationError({"employee": "Employee was not employed during this payroll period."})
        expected_gross = _model_money(self.basic + self.allowances + self.overtime_amount + self.other_earnings)
        expected_deductions = _model_money(self.advance_recovery + self.other_deductions)
        expected_net = _model_money(self.gross - self.total_deductions)
        if self.gross != expected_gross:
            raise ValidationError({"gross": "Employee gross pay does not match its earning components."})
        if self.total_deductions != expected_deductions:
            raise ValidationError({"total_deductions": "Employee deductions do not match their components."})
        if self.net != expected_net:
            raise ValidationError({"net": "Employee net pay must equal gross less deductions."})

    def __str__(self) -> str:
        return f"{self.run} · {self.employee_number}"


class PayrollRunLineComponent(CompanyOwnedModel):
    """Salary-structure contribution snapshot, including calendar-day proration when configured."""

    run_line = models.ForeignKey(PayrollRunLine, on_delete=models.PROTECT, related_name="components")
    salary_structure = models.ForeignKey(
        "internal_payroll.SalaryStructure",
        on_delete=models.PROTECT,
        related_name="payroll_line_components",
    )
    salary_structure_line = models.ForeignKey(
        "internal_payroll.SalaryStructureLine",
        on_delete=models.PROTECT,
        related_name="payroll_line_components",
    )
    component_code = models.CharField(max_length=30)
    component_name = models.CharField(max_length=160)
    component_category = models.CharField(max_length=20, choices=SalaryComponentCategory.choices)
    component_recurrence = models.CharField(max_length=20, choices=SalaryComponentRecurrence.choices)
    component_calculation = models.CharField(max_length=30, choices=SalaryComponentCalculation.choices)
    wps_mapping = models.CharField(max_length=30, choices=WPSMapping.choices)
    base_amount = money_field()
    effective_from = models.DateField()
    effective_to = models.DateField()
    proration_days = models.PositiveSmallIntegerField()
    proration_denominator = models.PositiveSmallIntegerField()
    amount = money_field()

    class Meta:
        db_table = "internal_payroll_run_line_component"
        ordering = ("component_category", "component_code", "effective_from")
        constraints = [
            models.UniqueConstraint(
                fields=("run_line", "salary_structure_line", "effective_from", "effective_to"),
                name="int_pay_comp_snapshot_uniq",
            ),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name="int_pay_comp_base_nonneg"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="int_pay_comp_amount_nonneg"),
            models.CheckConstraint(condition=Q(proration_days__gt=0), name="int_pay_comp_days_positive"),
            models.CheckConstraint(condition=Q(proration_denominator__gt=0), name="int_pay_comp_denom_positive"),
            models.CheckConstraint(condition=Q(effective_to__gte=models.F("effective_from")), name="int_pay_comp_date_range"),
            models.CheckConstraint(
                condition=Q(component_category__in=[value for value, _label in SalaryComponentCategory.choices]),
                name="int_pay_comp_category_valid",
            ),
            models.CheckConstraint(
                condition=Q(component_recurrence__in=[value for value, _label in SalaryComponentRecurrence.choices]),
                name="int_pay_comp_recur_valid",
            ),
            models.CheckConstraint(
                condition=Q(component_calculation__in=[value for value, _label in SalaryComponentCalculation.choices]),
                name="int_pay_comp_calc_valid",
            ),
            models.CheckConstraint(
                condition=Q(wps_mapping__in=[value for value, _label in WPSMapping.choices]),
                name="int_pay_comp_wps_valid",
            ),
        ]
        indexes = [models.Index(fields=("company", "run_line"), name="int_pay_comp_line_idx")]

    def clean(self) -> None:
        self.component_code = self.component_code.strip().upper()
        self.component_name = self.component_name.strip()
        if self.company_id and self.run_line_id and self.run_line.company_id != self.company_id:
            raise ValidationError({"run_line": "Payroll line must belong to the same company."})
        if self.company_id and self.salary_structure_id and self.salary_structure.company_id != self.company_id:
            raise ValidationError({"salary_structure": "Salary structure must belong to the same company."})
        if self.company_id and self.salary_structure_line_id and self.salary_structure_line.company_id != self.company_id:
            raise ValidationError({"salary_structure_line": "Salary structure line must belong to the same company."})


class PayrollRunLineAdjustment(CompanyOwnedModel):
    """Approved one-time transaction snapshotted into an employee payroll line."""

    run_line = models.ForeignKey(PayrollRunLine, on_delete=models.PROTECT, related_name="adjustments")
    adjustment = models.ForeignKey(PayrollAdjustment, on_delete=models.PROTECT, related_name="payroll_line_snapshots")
    adjustment_type = models.CharField(max_length=32)
    adjustment_label = models.CharField(max_length=100)
    transaction_date = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    reason = models.CharField(max_length=500)
    amount = money_field()
    effect = models.CharField(max_length=24, choices=(("earning", "Earning"), ("deduction", "Deduction"), ("advance_recovery", "Advance Recovery")))

    class Meta:
        db_table = "internal_payroll_run_line_adjustment"
        ordering = ("transaction_date", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("run_line", "adjustment"), name="int_pay_line_adj_uniq"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="int_pay_line_adj_amount_positive"),
            models.CheckConstraint(
                condition=Q(effect__in=["earning", "deduction", "advance_recovery"]),
                name="int_pay_line_adj_effect_valid",
            ),
        ]
        indexes = [models.Index(fields=("company", "run_line"), name="int_pay_line_adj_idx")]

    def clean(self) -> None:
        self.adjustment_label = self.adjustment_label.strip()
        self.reference = self.reference.strip().upper()
        self.reason = self.reason.strip()
        if self.company_id and self.run_line_id and self.run_line.company_id != self.company_id:
            raise ValidationError({"run_line": "Payroll line must belong to the same company."})
        if self.company_id and self.adjustment_id and self.adjustment.company_id != self.company_id:
            raise ValidationError({"adjustment": "Adjustment must belong to the same company."})
