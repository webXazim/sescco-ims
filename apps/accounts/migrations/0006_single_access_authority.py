from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


SYSTEM_PROFILE_KEY_BY_ROLE = {
    "owner": "role-owner",
    "operations-admin": "role-operations-admin",
    "access-admin": "role-access-admin",
    "inventory-manager": "role-inventory-manager",
    "storekeeper": "role-storekeeper",
    "finance": "role-finance",
    "internal-officer": "role-internal-officer",
    "rental-officer": "role-rental-officer",
    "reviewer": "role-reviewer",
    "auditor": "role-auditor",
}


def enforce_profile_authority(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Membership = apps.get_model("accounts", "CompanyMembership")
    AccessProfile = apps.get_model("accounts", "AccessProfile")

    # Django admin is reserved for superusers. Application access administrators are
    # ordinary authenticated users governed by CompanyMembership + AccessProfile.
    User.objects.using(db_alias).filter(is_superuser=False, is_staff=True).update(is_staff=False)
    User.objects.using(db_alias).filter(is_superuser=True, is_staff=False).update(is_staff=True)

    missing = Membership.objects.using(db_alias).filter(access_profile__isnull=True)
    for membership in missing.iterator(chunk_size=250):
        key = SYSTEM_PROFILE_KEY_BY_ROLE.get(membership.role)
        if key is None:
            raise RuntimeError(f"Unknown membership classification during 1.0.89 cutover: {membership.role}")
        profile = AccessProfile.objects.using(db_alias).filter(
            company_id=membership.company_id,
            key=key,
            is_system=True,
        ).first()
        if profile is None:
            raise RuntimeError(
                f"Missing system access profile {key!r} for company {membership.company_id} during 1.0.89 cutover."
            )
        Membership.objects.using(db_alias).filter(pk=membership.pk).update(access_profile_id=profile.pk)


def noop_reverse(apps, schema_editor):
    # Authority retirement is intentionally forward-only. Reintroducing User.role or
    # nullable access-profile authorization would create a second security authority.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_granular_access_authority"),
    ]

    operations = [
        migrations.RunPython(enforce_profile_authority, noop_reverse),
        migrations.AlterField(
            model_name="companymembership",
            name="access_profile",
            field=models.ForeignKey(
                help_text="Authoritative SESCCO application access profile. CompanyMembership.role is classification metadata only.",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="accounts.accessprofile",
            ),
        ),
        migrations.RemoveField(
            model_name="user",
            name="role",
        ),
    ]
