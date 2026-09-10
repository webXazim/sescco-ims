from __future__ import annotations

from calendar import monthrange
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import hours_field, rate_field
from apps.core.models import CompanyOwnedModel


class RentalTimesheetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    APPROVED = "approved", "Approved"
    LOCKED = "locked", "Locked"


class RentalAttendanceCode(models.TextChoices):
    ABSENT = "A", "Absent"
    NO_SCOPE = "N", "No Scope"
    LEAVE = "L", "Leave"
    OFF = "OFF", "Off"


class RentalTimesheetPeriod(CompanyOwnedModel):
    project = models.ForeignKey("projects.Project", on_delete=models.PROTECT, related_name="rental_timesheet_periods")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=16, choices=RentalTimesheetStatus.choices, default=RentalTimesheetStatus.DRAFT, db_index=True)
    revision = models.PositiveIntegerField(default=1)
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="submitted_rental_timesheets")
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_rental_timesheets")
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="locked_rental_timesheets")

    class Meta:
        db_table = "rental_timesheet_period"
        ordering = ("-period_start", "project__code")
        constraints = [
            models.UniqueConstraint(fields=("company", "project", "period_start"), name="rntl_ts_period_uniq"),
            models.CheckConstraint(condition=Q(period_end__gte=models.F("period_start")), name="rntl_ts_period_dates_chk"),
            models.CheckConstraint(condition=Q(revision__gte=1), name="rntl_ts_revision_chk"),
            models.CheckConstraint(condition=Q(status__in=[v for v, _ in RentalTimesheetStatus.choices]), name="rntl_ts_status_chk"),
        ]
        indexes = [models.Index(fields=("company", "project", "-period_start"), name="rntl_ts_project_period_idx")]

    def clean(self):
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({"project": "Project must belong to the same company."})
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Timesheet period must start on the first day of a month."})
        expected = self.period_start.replace(day=monthrange(self.period_start.year, self.period_start.month)[1])
        if self.period_end != expected:
            raise ValidationError({"period_end": "Timesheet period must end on the final day of the month."})


class RentalTimesheetEntry(CompanyOwnedModel):
    period = models.ForeignKey(RentalTimesheetPeriod, on_delete=models.PROTECT, related_name="entries")
    worker = models.ForeignKey("rental_manpower.RentalWorker", on_delete=models.PROTECT, related_name="timesheet_entries")
    assignment = models.ForeignKey("rental_manpower.WorkerAssignment", on_delete=models.PROTECT, related_name="timesheet_entries")
    work_date = models.DateField()
    regular_hours = hours_field(default=Decimal("0"))
    code = models.CharField(max_length=8, choices=RentalAttendanceCode.choices, blank=True)
    note = models.CharField(max_length=300, blank=True)
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)
    project_code = models.CharField(max_length=30)
    project_name = models.CharField(max_length=220)
    trade = models.CharField(max_length=120)
    rate_type = models.CharField(max_length=16)
    rate = rate_field()

    class Meta:
        db_table = "rental_timesheet_entry"
        ordering = ("work_date", "worker__worker_number")
        constraints = [
            models.UniqueConstraint(fields=("period", "worker", "work_date"), name="rntl_ts_entry_uniq"),
            models.CheckConstraint(condition=Q(regular_hours__gte=0) & Q(regular_hours__lte=24), name="rntl_ts_hours_chk"),
            models.CheckConstraint(condition=Q(code="") | Q(code__in=[v for v, _ in RentalAttendanceCode.choices]), name="rntl_ts_code_chk"),
            models.CheckConstraint(condition=Q(code="") | Q(regular_hours=0), name="rntl_ts_code_hours_chk"),
            models.CheckConstraint(condition=Q(rate__gt=0), name="rntl_ts_rate_chk"),
        ]
        indexes = [
            models.Index(fields=("company", "period", "worker"), name="rntl_ts_entry_worker_idx"),
            models.Index(fields=("company", "work_date"), name="rntl_ts_entry_date_idx"),
        ]

    def clean(self):
        self.note = (self.note or "").strip()
        if self.period_id and self.company_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "Timesheet period must belong to the same company."})
        if self.worker_id and self.company_id and self.worker.company_id != self.company_id:
            raise ValidationError({"worker": "Worker must belong to the same company."})
        if self.assignment_id and self.company_id and self.assignment.company_id != self.company_id:
            raise ValidationError({"assignment": "Assignment must belong to the same company."})
        if self.period_id and not (self.period.period_start <= self.work_date <= self.period.period_end):
            raise ValidationError({"work_date": "Work date must fall inside the timesheet period."})
        if self.assignment_id:
            if self.assignment.worker_id != self.worker_id or self.assignment.project_id != self.period.project_id:
                raise ValidationError({"assignment": "Assignment must match the worker and project."})
            if self.work_date < self.assignment.effective_from or (self.assignment.effective_to and self.work_date > self.assignment.effective_to):
                raise ValidationError({"assignment": "Assignment is not effective on the work date."})
        if self.code and self.regular_hours != Decimal("0"):
            raise ValidationError({"regular_hours": "Status-code rows cannot also contain regular hours."})


class RentalTimesheetOvertime(CompanyOwnedModel):
    period = models.ForeignKey(RentalTimesheetPeriod, on_delete=models.PROTECT, related_name="overtime_entries")
    worker = models.ForeignKey("rental_manpower.RentalWorker", on_delete=models.PROTECT, related_name="timesheet_overtime_entries")
    assignment = models.ForeignKey("rental_manpower.WorkerAssignment", on_delete=models.PROTECT, related_name="timesheet_overtime_entries")
    hours = hours_field()
    rate = rate_field()
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)
    project_code = models.CharField(max_length=30)
    project_name = models.CharField(max_length=220)
    trade = models.CharField(max_length=120)
    rate_type = models.CharField(max_length=16)

    class Meta:
        db_table = "rental_timesheet_overtime"
        constraints = [
            models.UniqueConstraint(fields=("period", "worker"), name="rntl_ts_ot_worker_uniq"),
            models.CheckConstraint(condition=Q(hours__gt=0) & Q(hours__lte=744), name="rntl_ts_ot_hours_chk"),
            models.CheckConstraint(condition=Q(rate__gt=0), name="rntl_ts_ot_rate_chk"),
        ]
        indexes = [models.Index(fields=("company", "period", "worker"), name="rntl_ts_ot_period_idx")]
