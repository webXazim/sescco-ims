from __future__ import annotations

from django.db import migrations, models


ROLE_CHOICES = [
    ("owner", "Company Owner"),
    ("operations-admin", "Operations Administrator"),
    ("access-admin", "Access Administrator"),
    ("inventory-manager", "Inventory Manager"),
    ("storekeeper", "Storekeeper"),
    ("finance", "Finance Manager"),
    ("internal-officer", "Internal Payroll Officer"),
    ("rental-officer", "Rental Manpower Officer"),
    ("rental-supervisor", "Rental Supervisor / Foreman"),
    ("reviewer", "Finance Reviewer"),
    ("auditor", "Read-only Auditor"),
    ("custom", "Custom Access Profile"),
]

FOREMAN_PERMISSIONS = (
    "rental.overview.view",
    "rental.workers.view",
    "rental.assignments.view",
    "rental.timesheets.view",
    "rental.timesheets.edit",
    "rental.timesheets.submit",
    "rental.overtime.view",
    "rental.overtime.edit",
    "rental.overtime.submit",
)


def create_foreman_profiles(apps, schema_editor):
    Company = apps.get_model("accounts", "Company")
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    AccessProfilePermission = apps.get_model("accounts", "AccessProfilePermission")
    for company in Company.objects.all().iterator():
        profile, _created = AccessProfile.objects.update_or_create(
            company=company,
            key="role-rental-supervisor",
            defaults={
                "name": "Rental Supervisor / Foreman",
                "description": (
                    "Project-scoped Rental workforce supervision for worker visibility, "
                    "timesheet/overtime entry and submit-for-review only."
                ),
                "is_system": True,
                "is_active": True,
            },
        )
        AccessProfilePermission.objects.filter(profile=profile).exclude(permission__in=FOREMAN_PERMISSIONS).delete()
        existing = set(AccessProfilePermission.objects.filter(profile=profile).values_list("permission", flat=True))
        AccessProfilePermission.objects.bulk_create(
            [AccessProfilePermission(profile=profile, permission=permission) for permission in FOREMAN_PERMISSIONS if permission not in existing],
            ignore_conflicts=True,
        )


def remove_foreman_profiles(apps, schema_editor):
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    AccessProfile.objects.filter(key="role-rental-supervisor", is_system=True).delete()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0007_user_management_backend")]

    operations = [
        migrations.RemoveConstraint(model_name="companymembership", name="accounts_membership_role_valid"),
        migrations.AlterField(
            model_name="companymembership",
            name="role",
            field=models.CharField(
                choices=ROLE_CHOICES,
                help_text="Compatibility classification only; AccessProfile is the authorization authority.",
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name="companymembership",
            constraint=models.CheckConstraint(
                condition=models.Q(role__in=[value for value, _label in ROLE_CHOICES]),
                name="accounts_membership_role_valid",
            ),
        ),
        migrations.RunPython(create_foreman_profiles, remove_foreman_profiles),
    ]
