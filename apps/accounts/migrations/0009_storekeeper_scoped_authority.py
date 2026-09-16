from __future__ import annotations

from django.db import migrations


STOREKEEPER_PERMISSIONS = (
    "inventory.dashboard.view",
    "inventory.stock.view",
    "inventory.stock.receive",
    "inventory.stock.issue",
    "inventory.stock.transfer",
    "inventory.movements.view",
    "inventory.projects.view",
    "inventory.suppliers.view",
    "inventory.locations.view",
    "inventory.export.execute",
    "shared.search.use",
)


def reconcile_storekeeper_profiles(apps, schema_editor):
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    AccessProfilePermission = apps.get_model("accounts", "AccessProfilePermission")
    profiles = AccessProfile.objects.filter(key="role-storekeeper", is_system=True)
    for profile in profiles.iterator():
        AccessProfilePermission.objects.filter(profile=profile).exclude(
            permission__in=STOREKEEPER_PERMISSIONS
        ).delete()
        existing = set(
            AccessProfilePermission.objects.filter(profile=profile).values_list("permission", flat=True)
        )
        AccessProfilePermission.objects.bulk_create(
            [
                AccessProfilePermission(profile=profile, permission=permission)
                for permission in STOREKEEPER_PERMISSIONS
                if permission not in existing
            ],
            ignore_conflicts=True,
        )


def noop_reverse(apps, schema_editor):
    # The preceding profile grants are retained on reverse. Reconstructing the wider
    # pre-1.0.93 capability-derived profile would weaken the security boundary.
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0008_rental_supervisor_profile")]

    operations = [
        migrations.RunPython(reconcile_storekeeper_profiles, noop_reverse),
    ]
