from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

project_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    message="Use letters, numbers, hyphens, or underscores; start with a letter or number.",
)


class Project(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ARCHIVED = "archived", "Archived"

    code = models.CharField(
        max_length=30,
        unique=True,
        validators=[project_code_validator],
        help_text="Short project tag shown across inventory, for example ARAMCO-01.",
    )
    name = models.CharField(max_length=180)
    client_name = models.CharField(max_length=180, blank=True)
    location = models.CharField(max_length=180, blank=True)
    start_date = models.DateField(blank=True, null=True)
    expected_completion_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
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

    class Meta:
        ordering = ("code",)
        indexes = [
            models.Index(fields=("status", "code"), name="project_status_code_idx"),
            models.Index(fields=("name",), name="project_name_idx"),
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
            errors["expected_completion_date"] = "Completion date cannot be before the start date."
        if self.pk and self.status in {self.Status.COMPLETED, self.Status.ARCHIVED}:
            original_status = (
                type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            )
            if (
                original_status != self.status
                and self.stock_items.filter(current_quantity__gt=0).exists()
            ):
                errors["status"] = (
                    "A project can be completed or archived only after every stock balance is zero."
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        self.name = " ".join(self.name.split())
        self.client_name = " ".join(self.client_name.split())
        self.location = " ".join(self.location.split())
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def accepts_stock_activity(self) -> bool:
        return self.status == self.Status.ACTIVE and self.deleted_at is None
