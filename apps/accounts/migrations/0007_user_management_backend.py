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
    ("reviewer", "Finance Reviewer"),
    ("auditor", "Read-only Auditor"),
    ("custom", "Custom Access Profile"),
]


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_single_access_authority")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="credentials_updated_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="must_change_password",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.RemoveConstraint(
            model_name="companymembership",
            name="accounts_membership_role_valid",
        ),
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
    ]
