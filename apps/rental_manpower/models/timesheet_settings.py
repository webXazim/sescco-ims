from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models

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
