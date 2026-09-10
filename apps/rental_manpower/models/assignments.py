from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import rate_field
from apps.core.models import CompanyOwnedModel


class RentalRateType(models.TextChoices):
    HOURLY = "hourly", "Hourly"
    DAILY = "daily", "Daily"
    MONTHLY = "monthly", "Monthly"


class AssignmentChangeType(models.TextChoices):
    ASSIGNMENT = "assignment", "Project assignment"
    TRANSFER = "transfer", "Project transfer"
    TRADE_CHANGE = "trade_change", "Trade change"
    RATE_CHANGE = "rate_change", "Rate change"


class ReleaseDisposition(models.TextChoices):
    AVAILABLE = "available", "Available"
    INACTIVE = "inactive", "Inactive"


class WorkerAssignment(CompanyOwnedModel):
    """Effective-dated rental-worker deployment and commercial-rate history.

    Each row is one contiguous segment. Project/trade/rate changes close the preceding
    segment and create a new one; historical rows are never rewritten into the new terms.
    """

    worker = models.ForeignKey(
        "rental_manpower.RentalWorker",
        on_delete=models.PROTECT,
        related_name="rental_assignments",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="rental_assignments",
    )
    trade = models.CharField(max_length=120)
    rate_type = models.CharField(max_length=16, choices=RentalRateType.choices)
    rate = rate_field()
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    change_type = models.CharField(
        max_length=20,
        choices=AssignmentChangeType.choices,
        default=AssignmentChangeType.ASSIGNMENT,
    )
    reason = models.CharField(max_length=300, blank=True)
    end_reason = models.CharField(max_length=300, blank=True)
    end_notes = models.TextField(blank=True)
    release_disposition = models.CharField(
        max_length=16,
        choices=ReleaseDisposition.choices,
        blank=True,
    )
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "rental_worker_assignment"
        ordering = ("worker_id", "effective_from", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "worker"),
                condition=Q(effective_to__isnull=True, cancelled_at__isnull=True),
                name="rntl_asg_open_uniq",
            ),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="rntl_asg_dates_chk",
            ),
            models.CheckConstraint(condition=Q(rate__gt=0), name="rntl_asg_rate_pos_chk"),
            models.CheckConstraint(
                condition=Q(rate_type__in=[value for value, _label in RentalRateType.choices]),
                name="rntl_asg_rate_type_chk",
            ),
            models.CheckConstraint(
                condition=Q(change_type__in=[value for value, _label in AssignmentChangeType.choices]),
                name="rntl_asg_change_type_chk",
            ),
            models.CheckConstraint(
                condition=Q(release_disposition="")
                | Q(release_disposition__in=[value for value, _label in ReleaseDisposition.choices]),
                name="rntl_asg_release_disp_chk",
            ),
            models.CheckConstraint(
                condition=Q(release_disposition="") | Q(effective_to__isnull=False),
                name="rntl_asg_release_end_chk",
            ),
            models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | Q(effective_to__isnull=True, release_disposition=""),
                name="rntl_asg_cancel_state_chk",
            ),
            models.CheckConstraint(
                condition=Q(cancelled_at__isnull=True) | ~Q(cancel_reason=""),
                name="rntl_asg_cancel_reason_chk",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "worker", "effective_from"), name="rntl_asg_worker_date_idx"),
            models.Index(fields=("company", "project", "effective_from"), name="rntl_asg_project_date_idx"),
            models.Index(fields=("company", "effective_from", "effective_to"), name="rntl_asg_dates_idx"),
        ]

    def clean(self) -> None:
        self.trade = (self.trade or "").strip()
        self.reason = (self.reason or "").strip()
        self.end_reason = (self.end_reason or "").strip()
        self.end_notes = (self.end_notes or "").strip()
        self.cancel_reason = (self.cancel_reason or "").strip()
        if not self.trade:
            raise ValidationError({"trade": "Trade / role is required."})
        if self.rate is None or self.rate <= 0:
            raise ValidationError({"rate": "Assignment rate must be greater than zero."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Assignment end date cannot be before its start date."})
        if self.worker_id and self.company_id and self.worker.company_id != self.company_id:
            raise ValidationError({"worker": "Worker must belong to the same company."})
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({"project": "Project must belong to the same company."})
        if self.release_disposition and not self.effective_to:
            raise ValidationError({"release_disposition": "A release disposition requires an assignment end date."})
        if self.cancelled_at and self.effective_to is not None:
            raise ValidationError({"cancelled_at": "A cancelled scheduled assignment cannot also carry worked assignment dates."})
        if self.cancelled_at and not self.cancel_reason:
            raise ValidationError({"cancel_reason": "A cancellation reason is required."})

    def __str__(self) -> str:
        end = "cancelled" if self.cancelled_at else (self.effective_to.isoformat() if self.effective_to else "current")
        return f"{self.worker} · {self.project} · {self.effective_from.isoformat()} → {end}"
