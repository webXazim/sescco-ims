from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

from .base import UUIDTimeStampedModel

if TYPE_CHECKING:
    from .company import Company


class CompanyScopedQuerySet(models.QuerySet):
    """Explicit tenant-scoping helper for company-owned records."""

    def for_company(self, company: Company | object) -> "CompanyScopedQuerySet":
        company_id = getattr(company, "pk", company)
        return self.filter(company_id=company_id)


class CompanyScopedManager(models.Manager.from_queryset(CompanyScopedQuerySet)):
    pass


class CompanyOwnedModel(UUIDTimeStampedModel):
    """Abstract base for new records that belong to exactly one company.

    Existing IMS inventory/project models will receive additive company foreign keys in Upgrade 4
    and keep their existing primary keys, so they intentionally do not inherit this class.
    """

    company = models.ForeignKey(
        "core.Company",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_records",
    )

    objects = CompanyScopedManager()

    class Meta:
        abstract = True
