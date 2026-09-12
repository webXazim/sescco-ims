from __future__ import annotations

from django.conf import settings
from django.db import models

from .base import UUIDTimeStampedModel
from .scoping import CompanyScopedManager


class TrashCascadeLink(UUIDTimeStampedModel):
    """Tracks child masters moved to Trash by a recoverable parent delete.

    The link is deliberately separate from audit history: it is mutable recovery
    state used only to restore the exact children changed by the parent delete.
    Historical/independently deleted children are never claimed by a cascade.
    """

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="trash_cascade_links",
    )
    root_type = models.CharField(max_length=120, db_index=True)
    root_id = models.CharField(max_length=64, db_index=True)
    child_type = models.CharField(max_length=120, db_index=True)
    child_id = models.CharField(max_length=64, db_index=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="trash_cascade_links_created",
    )
    reason = models.CharField(max_length=500, blank=True)
    restored_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = CompanyScopedManager()

    class Meta:
        db_table = "core_trash_cascade_link"
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("company", "root_type", "root_id", "child_type", "child_id"),
                condition=models.Q(restored_at__isnull=True),
                name="core_trash_cascade_active_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("company", "root_type", "root_id", "restored_at"),
                name="core_trash_cascade_root_idx",
            ),
            models.Index(
                fields=("company", "child_type", "child_id", "restored_at"),
                name="core_trash_cascade_child_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.root_type}:{self.root_id} -> {self.child_type}:{self.child_id}"
