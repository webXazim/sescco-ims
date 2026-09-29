from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from decimal import Decimal

from apps.core.models import CompanyOwnedModel


RENTAL_TIMESHEET_WEEKDAY_KEYS = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")


def default_rental_timesheet_off_weekdays():
    # Preserve the existing Saudi project-timesheet visual default until a project
    # explicitly chooses another weekly off-day pattern.
    return ["fri", "sat"]


class RentalTimesheetProjectSettings(CompanyOwnedModel):
    """Project-scoped display/calendar preferences for Rental timesheets.

    This model deliberately lives outside models/timesheets.py. That file is part of
    the immutable pre-v3 payroll-document authority and its hash is protected by the
    staged document migration freeze.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="rental_timesheet_settings",
    )
    off_weekdays = models.JSONField(default=default_rental_timesheet_off_weekdays)
    regular_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    overtime_multiplier = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("1.0000"))
    automatic_overtime = models.BooleanField(default=True)

    class Meta:
        db_table = "rental_timesheet_project_settings"
        ordering = ("project__code",)

    def clean(self):
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({"project": "Project must belong to the same company."})

        raw = self.off_weekdays if isinstance(self.off_weekdays, list) else []
        values = []
        for value in raw:
            key = str(value or "").strip().lower()
            if key not in RENTAL_TIMESHEET_WEEKDAY_KEYS:
                raise ValidationError({"off_weekdays": f"Unknown weekday: {value}."})
            if key not in values:
                values.append(key)
        self.off_weekdays = values
        if self.regular_hours_per_day is None or not (Decimal("0") < self.regular_hours_per_day <= Decimal("24")):
            raise ValidationError({"regular_hours_per_day": "Regular working hours must be greater than 0 and no more than 24."})
        if self.overtime_multiplier is None or not (Decimal("1") <= self.overtime_multiplier <= Decimal("10")):
            raise ValidationError({"overtime_multiplier": "OT multiplier must be at least 1.00 and no more than 10.00."})


class RentalTimesheetPeriodPolicy(CompanyOwnedModel):
    """Immutable-after-Draft policy snapshot for one Rental project-period.

    Project settings are the template for future periods. The period snapshot prevents
    later configuration changes from changing historical hour splits or OT valuation.
    """

    period = models.OneToOneField(
        "rental_manpower.RentalTimesheetPeriod",
        on_delete=models.PROTECT,
        related_name="policy_snapshot",
    )
    off_weekdays = models.JSONField(default=default_rental_timesheet_off_weekdays)
    regular_hours_per_day = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("10.00"))
    overtime_multiplier = models.DecimalField(max_digits=6, decimal_places=4, default=Decimal("1.0000"))
    automatic_overtime = models.BooleanField(default=True)

    class Meta:
        db_table = "rental_timesheet_period_policy"
        ordering = ("-period__period_start", "period__project__code")

    def clean(self):
        if self.period_id and self.company_id and self.period.company_id != self.company_id:
            raise ValidationError({"period": "Timesheet period must belong to the same company."})
        raw = self.off_weekdays if isinstance(self.off_weekdays, list) else []
        values = []
        for value in raw:
            key = str(value or "").strip().lower()
            if key not in RENTAL_TIMESHEET_WEEKDAY_KEYS:
                raise ValidationError({"off_weekdays": f"Unknown weekday: {value}."})
            if key not in values:
                values.append(key)
        self.off_weekdays = values
        if self.regular_hours_per_day is None or not (Decimal("0") < self.regular_hours_per_day <= Decimal("24")):
            raise ValidationError({"regular_hours_per_day": "Regular working hours must be greater than 0 and no more than 24."})
        if self.overtime_multiplier is None or not (Decimal("1") <= self.overtime_multiplier <= Decimal("10")):
            raise ValidationError({"overtime_multiplier": "OT multiplier must be at least 1.00 and no more than 10.00."})
