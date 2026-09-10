from __future__ import annotations

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.utils import NotSupportedError

from .base import UUIDTimeStampedModel


class AuditArea(models.TextChoices):
    ACCESS = "access", "Access"
    CORE = "core", "Platform Core"
    PROJECTS = "projects", "Projects"
    INVENTORY = "inventory", "Inventory"
    DATA_EXCHANGE = "data_exchange", "Data Exchange"
    INTERNAL = "internal", "Internal Payroll"
    RENTAL = "rental", "Rental Manpower"
    DOCUMENTS = "documents", "Documents"
    MANAGEMENT = "management", "Management"


class ImmutableAuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise NotSupportedError("Audit events are immutable and cannot be updated.")

    def delete(self):
        raise NotSupportedError("Audit events are immutable and cannot be deleted.")


class ImmutableAuditManager(models.Manager.from_queryset(ImmutableAuditQuerySet)):
    pass


class AuditEvent(UUIDTimeStampedModel):
    """Append-only cross-module audit record for sensitive state changes."""

    company = models.ForeignKey("core.Company", on_delete=models.PROTECT, related_name="audit_events")
    area = models.CharField(max_length=20, choices=AuditArea.choices, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=120, db_index=True)
    object_id = models.CharField(max_length=64, db_index=True)
    object_label = models.CharField(max_length=240, blank=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_audit_events",
    )
    # Upgrade 3 introduces UUID CompanyMembership records. Keep this nullable until then so the
    # platform audit service can already capture the existing IMS user safely.
    actor_membership_id = models.UUIDField(null=True, blank=True)
    actor_role = models.CharField(max_length=40, blank=True)
    actor_username = models.CharField(max_length=150, blank=True)
    actor_display_name = models.CharField(max_length=300, blank=True)
    actor_email = models.EmailField(blank=True)

    before = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    metadata = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)

    # IMS deliberately accepts opaque upstream request IDs, so this cannot safely be UUIDField.
    request_id = models.CharField(max_length=64, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    objects = ImmutableAuditManager()

    class Meta:
        db_table = "core_audit_event"
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("company", "-created_at"), name="core_audit_company_time_idx"),
            models.Index(fields=("company", "area", "-created_at"), name="core_audit_area_time_idx"),
            models.Index(fields=("company", "object_type", "object_id"), name="core_audit_object_idx"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise NotSupportedError("Audit events are immutable and cannot be updated.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise NotSupportedError("Audit events are immutable and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.company} · {self.action} · {self.object_type}:{self.object_id}"
