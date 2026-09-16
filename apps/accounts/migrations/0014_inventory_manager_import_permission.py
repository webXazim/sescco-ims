from __future__ import annotations

from django.db import migrations


PROFILE_KEY = "role-inventory-manager"
PERMISSION = "inventory.import.execute"


def reconcile_inventory_manager_import_permission(apps, schema_editor):
    db = schema_editor.connection.alias
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    AccessProfilePermission = apps.get_model("accounts", "AccessProfilePermission")

    profile_ids = list(
        AccessProfile.objects.using(db)
        .filter(key=PROFILE_KEY, is_system=True, is_active=True)
        .values_list("pk", flat=True)
    )
    if not profile_ids:
        return

    existing = set(
        AccessProfilePermission.objects.using(db)
        .filter(profile_id__in=profile_ids, permission=PERMISSION)
        .values_list("profile_id", flat=True)
    )
    missing_rows = [
        AccessProfilePermission(profile_id=profile_id, permission=PERMISSION)
        for profile_id in profile_ids
        if profile_id not in existing
    ]
    if missing_rows:
        AccessProfilePermission.objects.using(db).bulk_create(
            missing_rows,
            batch_size=250,
            ignore_conflicts=True,
        )


def noop_reverse(apps, schema_editor):
    # Do not silently remove Inventory Manager import authority on rollback. The
    # permission is part of the current authoritative built-in profile template.
    pass


class Migration(migrations.Migration):
    dependencies = [("accounts", "0013_rename_access_profile_index")]

    operations = [
        migrations.RunPython(
            reconcile_inventory_manager_import_permission,
            noop_reverse,
        ),
    ]
