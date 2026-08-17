from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.projects.models import Project

from .models import InventoryLocation


@receiver(post_save, sender=Project)
def ensure_project_inventory_location(sender, instance, **kwargs):
    if kwargs.get("raw"):
        return
    code = instance.code
    conflict = InventoryLocation.objects.filter(code=code).exclude(project=instance).exists()
    if conflict:
        base = f"PROJECT-{instance.code}"[:30]
        code = base
        suffix = 1
        while InventoryLocation.objects.filter(code=code).exclude(project=instance).exists():
            suffix += 1
            code = f"{base[: 29 - len(str(suffix))]}-{suffix}"
    InventoryLocation.objects.update_or_create(
        project=instance,
        defaults={
            "code": code,
            "name": instance.name,
            "location_type": InventoryLocation.Type.PROJECT,
            "is_active": instance.deleted_at is None,
        },
    )
