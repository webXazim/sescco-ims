from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.core.models import Company, CompanySettings


@receiver(post_save, sender=Company, dispatch_uid="core.ensure_company_settings")
def ensure_company_settings(sender, instance: Company, created: bool, **kwargs) -> None:
    if created:
        CompanySettings.objects.get_or_create(company=instance)
