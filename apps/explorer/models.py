from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class SavedView(models.Model):
    class ViewType(models.TextChoices):
        INVENTORY = "inventory", "Current inventory"
        ACTIVITY = "activity", "Stock activity"
        LOW_STOCK = "low_stock", "Low stock"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="saved_inventory_views",
    )
    name = models.CharField(max_length=100)
    view_type = models.CharField(max_length=24, choices=ViewType.choices)
    query_params = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("view_type", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "view_type", "name"),
                name="uniq_saved_view_name_per_owner_type",
            )
        ]
        indexes = [
            models.Index(fields=("owner", "view_type"), name="saved_view_owner_type_idx")
        ]

    def __str__(self) -> str:
        return f"{self.owner} · {self.get_view_type_display()} · {self.name}"

    def clean(self) -> None:
        super().clean()
        self.name = " ".join((self.name or "").split())
        if not self.name:
            raise ValidationError({"name": "Saved view name is required."})
        if not isinstance(self.query_params, dict):
            raise ValidationError({"query_params": "Saved filters must be a key-value object."})

    def save(self, *args, **kwargs):
        self.name = " ".join((self.name or "").split())
        self.full_clean()
        return super().save(*args, **kwargs)


class TablePreference(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="inventory_table_preferences",
    )
    view_type = models.CharField(max_length=24, choices=SavedView.ViewType.choices)
    columns = models.JSONField(default=list)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("owner", "view_type")
        constraints = [
            models.UniqueConstraint(
                fields=("owner", "view_type"),
                name="uniq_table_preference_owner_view",
            )
        ]

    def __str__(self) -> str:
        return f"{self.owner} · {self.get_view_type_display()} columns"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.columns, list) or not all(
            isinstance(column, str) for column in self.columns
        ):
            raise ValidationError({"columns": "Columns must be a list of column names."})
