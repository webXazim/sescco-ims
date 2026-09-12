from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import CompanyScopedManager

project_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    message="Use letters, numbers, hyphens, or underscores; start with a letter or number.",
)


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_HOLD = "on_hold", "On Hold"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="projects",
    )
    # Public cross-module identity. Existing IMS integer PKs remain untouched so all
    # production Inventory foreign keys stay stable during the Payroll merge.
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    code = models.CharField(
        max_length=30,
        validators=[project_code_validator],
        help_text="Short project tag shown across inventory, for example ARAMCO-01.",
    )
    name = models.CharField(max_length=180)
    client_name = models.CharField(max_length=180, blank=True)
    location = models.CharField(max_length=180, blank=True)
    start_date = models.DateField(blank=True, null=True)
    expected_completion_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(
        blank=True,
        null=True,
        help_text="Actual project end date. Required when a project is newly completed.",
    )
    manager_name = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    archived_at = models.DateTimeField(blank=True, null=True, db_index=True)
    archived_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    deleted_at = models.DateTimeField(blank=True, null=True, db_index=True)
    purge_after = models.DateTimeField(blank=True, null=True, db_index=True)
    deletion_reason = models.TextField(blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="projects_deleted",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="projects_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="projects_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("company", "status", "code"), name="project_company_status_idx"),
            models.Index(fields=("company", "start_date"), name="project_company_start_idx"),
            models.Index(fields=("status", "code"), name="project_status_code_idx"),
            models.Index(fields=("name",), name="project_name_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="projects_company_code_uniq"),
            models.CheckConstraint(
                condition=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F("start_date")),
                name="project_end_after_start_chk",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"

    def clean(self) -> None:
        super().clean()
        errors = {}
        if (
            self.start_date
            and self.expected_completion_date
            and self.expected_completion_date < self.start_date
        ):
            errors["expected_completion_date"] = "Expected completion cannot be before the start date."
        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "Actual end date cannot be before the start date."

        original_status = None
        if self.pk and self.company_id:
            original_status = (
                type(self).objects.filter(pk=self.pk, company_id=self.company_id)
                .values_list("status", flat=True)
                .first()
            )
        if self.status == self.Status.COMPLETED and original_status != self.Status.COMPLETED and not self.end_date:
            errors["end_date"] = "Set the actual end date before completing the project."
        if self.pk and self.status in {self.Status.COMPLETED, self.Status.ARCHIVED}:
            if (
                original_status != self.status
                and self.stock_items.filter(current_quantity__gt=0).exists()
            ):
                errors["status"] = (
                    "A project can be completed or archived only after every stock balance is zero."
                )
            if original_status != self.status and hasattr(self, "rental_assignments"):
                rental_rows = self.rental_assignments.filter(cancelled_at__isnull=True)
                if self.status == self.Status.COMPLETED and self.end_date:
                    rental_rows = rental_rows.filter(
                        models.Q(effective_to__isnull=True) | models.Q(effective_to__gt=self.end_date)
                    )
                else:
                    rental_rows = rental_rows.filter(effective_to__isnull=True)
                if rental_rows.exists():
                    errors["status"] = (
                        "Release or transfer open rental manpower assignments before completing or archiving the project."
                    )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.name = " ".join(self.name.split())
        self.client_name = " ".join(self.client_name.split())
        self.location = " ".join(self.location.split())
        self.manager_name = " ".join(self.manager_name.split())
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def accepts_stock_activity(self) -> bool:
        return self.status == self.Status.ACTIVE and self.deleted_at is None

    @property
    def accepts_rental_assignment(self) -> bool:
        """Whether new Rental Manpower assignments may target this project."""

        return self.status == self.Status.ACTIVE and self.deleted_at is None

    def covers_work_date(self, work_date) -> bool:
        """Return whether a payroll/inventory operational date is inside the project schedule."""

        if self.start_date and work_date < self.start_date:
            return False
        if self.end_date and work_date > self.end_date:
            return False
        return True
