from __future__ import annotations

from calendar import monthrange
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import hours_field, money_field, rate_field
from apps.core.models import CompanyOwnedModel


class AttendancePeriodStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    LOCKED = "locked", "Locked"


class AttendanceCode(models.TextChoices):
    ABSENT = "A", "Absent"
    LEAVE = "L", "Leave"
    SICK = "S", "Sick"
    HOLIDAY = "H", "Holiday"
    OFF = "OFF", "Off"


class AttendancePeriod(CompanyOwnedModel):
    """One controlled monthly attendance/overtime input period for internal employees."""

    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=AttendancePeriodStatus.choices,
        default=AttendancePeriodStatus.DRAFT,
        db_index=True,
    )
    revision = models.PositiveIntegerField(default=1)

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_internal_attendance_periods",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_internal_attendance_periods",
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="locked_internal_attendance_periods",
    )

    class Meta:
        db_table = "internal_attendance_period"
        ordering = ("-period_start",)
        constraints = [
            models.UniqueConstraint(
                fields=("company", "period_start"),
                name="int_att_period_company_month_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in AttendancePeriodStatus.choices]),
                name="int_att_period_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(period_end__gte=models.F("period_start")),
                name="int_att_period_valid_range",
            ),
            models.CheckConstraint(condition=Q(revision__gte=1), name="int_att_period_revision_positive"),
        ]
        indexes = [
            models.Index(fields=("company", "status", "-period_start"), name="int_att_period_status_idx"),
        ]

    def clean(self) -> None:
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Attendance period must start on the first day of a month."})
        expected_end_day = monthrange(self.period_start.year, self.period_start.month)[1]
        expected_end = self.period_start.replace(day=expected_end_day)
        if self.period_end != expected_end:
            raise ValidationError({"period_end": "Attendance period must end on the final day of the same month."})

    def __str__(self) -> str:
        return f"{self.company} · {self.period_start:%B %Y} · {self.get_status_display()}"


class AttendanceEntry(CompanyOwnedModel):
    """Explicit daily attendance value. Missing row means the date has not been completed."""

    period = models.ForeignKey(AttendancePeriod, on_delete=models.PROTECT, related_name="entries")
    employee = models.ForeignKey(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="attendance_entries",
    )
    work_date = models.DateField()
    regular_hours = hours_field(default=Decimal("0"))
    code = models.CharField(max_length=8, choices=AttendanceCode.choices, blank=True)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "internal_attendance_entry"
        ordering = ("work_date", "employee__employee_number")
        constraints = [
            models.UniqueConstraint(
                fields=("period", "employee", "work_date"),
                name="int_att_entry_period_emp_date_uniq",
            ),
            models.CheckConstraint(
                condition=Q(regular_hours__gte=0) & Q(regular_hours__lte=24),
                name="int_att_entry_hours_range",
            ),
            models.CheckConstraint(
                condition=Q(code="") | Q(code__in=[value for value, _label in AttendanceCode.choices]),
                name="int_att_entry_code_valid",
            ),
            models.CheckConstraint(
                condition=Q(code="") | Q(regular_hours=0),
                name="int_att_entry_code_zero_hours",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "period", "employee"), name="int_att_entry_period_emp_idx"),
            models.Index(fields=("company", "work_date"), name="int_att_entry_date_idx"),
        ]

    def clean(self) -> None:
        self.note = self.note.strip()
        if self.company_id and self.period_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "Attendance period must belong to the same company."})
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.period_id and not (self.period.period_start <= self.work_date <= self.period.period_end):
            raise ValidationError({"work_date": "Attendance date must fall inside the attendance period."})
        if self.employee_id:
            if self.work_date < self.employee.joining_date:
                raise ValidationError({"work_date": "Attendance cannot be recorded before the employee joining date."})
            if self.employee.employment_end_date and self.work_date > self.employee.employment_end_date:
                raise ValidationError({"work_date": "Attendance cannot be recorded after the employee employment end date."})
        if self.regular_hours is None or self.regular_hours < 0 or self.regular_hours > 24:
            raise ValidationError({"regular_hours": "Regular hours must be between 0 and 24."})
        if self.code and self.regular_hours != Decimal("0"):
            raise ValidationError({"regular_hours": "Status-code attendance rows cannot also contain regular hours."})

    def __str__(self) -> str:
        value = self.code or f"{self.regular_hours}h"
        return f"{self.employee} · {self.work_date.isoformat()} · {value}"


class AttendanceOvertimeEntry(CompanyOwnedModel):
    """Monthly employee overtime input with an immutable salary/policy calculation snapshot."""

    period = models.ForeignKey(AttendancePeriod, on_delete=models.PROTECT, related_name="overtime_entries")
    employee = models.ForeignKey(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="attendance_overtime_entries",
    )
    salary_structure = models.ForeignKey(
        "internal_payroll.SalaryStructure",
        on_delete=models.PROTECT,
        related_name="attendance_overtime_entries",
    )
    hours = hours_field()

    policy_code = models.CharField(max_length=30)
    policy_name = models.CharField(max_length=160)
    base_component_code = models.CharField(max_length=30)
    base_component_name = models.CharField(max_length=160)
    base_amount = money_field()
    divisor = rate_field()
    multiplier = rate_field()
    overtime_rate = rate_field()
    amount = money_field()

    class Meta:
        db_table = "internal_attendance_overtime_entry"
        ordering = ("employee__employee_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("period", "employee"),
                name="int_att_ot_period_emp_uniq",
            ),
            models.CheckConstraint(condition=Q(hours__gt=0), name="int_att_ot_hours_positive"),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name="int_att_ot_base_nonnegative"),
            models.CheckConstraint(condition=Q(divisor__gt=0), name="int_att_ot_divisor_positive"),
            models.CheckConstraint(condition=Q(multiplier__gt=0), name="int_att_ot_multiplier_positive"),
            models.CheckConstraint(condition=Q(overtime_rate__gte=0), name="int_att_ot_rate_nonnegative"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="int_att_ot_amount_nonnegative"),
        ]
        indexes = [
            models.Index(fields=("company", "period", "employee"), name="int_att_ot_period_emp_idx"),
        ]

    def clean(self) -> None:
        self.policy_code = self.policy_code.strip().upper()
        self.policy_name = self.policy_name.strip()
        self.base_component_code = self.base_component_code.strip().upper()
        self.base_component_name = self.base_component_name.strip()
        if self.company_id and self.period_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "Attendance period must belong to the same company."})
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.company_id and self.salary_structure_id and self.salary_structure.company_id != self.company_id:
            raise ValidationError({"salary_structure": "Salary structure must belong to the same company."})
        if self.employee_id and self.salary_structure_id and self.salary_structure.employee_id != self.employee_id:
            raise ValidationError({"salary_structure": "Salary structure must belong to the overtime employee."})
        if self.hours is None or self.hours <= 0:
            raise ValidationError({"hours": "Overtime hours must be greater than zero."})
        if self.divisor is None or self.divisor <= 0:
            raise ValidationError({"divisor": "Overtime divisor must be greater than zero."})
        if self.multiplier is None or self.multiplier <= 0:
            raise ValidationError({"multiplier": "Overtime multiplier must be greater than zero."})

    def __str__(self) -> str:
        return f"{self.employee} · {self.period.period_start:%B %Y} · {self.hours}h OT"
