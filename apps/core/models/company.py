from __future__ import annotations

from django.db import models

from .base import UUIDTimeStampedModel


class Company(UUIDTimeStampedModel):
    """Top-level tenant/business boundary for the merged platform."""

    name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=250, blank=True)
    slug = models.SlugField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "core_company"
        ordering = ("name",)
        verbose_name_plural = "companies"

    def __str__(self) -> str:
        return self.name
