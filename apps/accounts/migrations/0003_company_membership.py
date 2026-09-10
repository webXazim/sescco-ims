import uuid

import django.db.models.deletion
from django.db import migrations, models


ROLE_CHOICES = [
    ("owner", "Company Owner"),
    ("operations-admin", "Operations Administrator"),
    ("inventory-manager", "Inventory Manager"),
    ("storekeeper", "Storekeeper"),
    ("finance", "Finance Manager"),
    ("internal-officer", "Internal Payroll Officer"),
    ("rental-officer", "Rental Manpower Officer"),
    ("reviewer", "Finance Reviewer"),
    ("auditor", "Read-only Auditor"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_alter_user_groups"),
        ("core", "0001_platform_core"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyMembership",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=ROLE_CHOICES, max_length=32)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("joined_at", models.DateTimeField(auto_now_add=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="memberships",
                        to="core.company",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="company_memberships",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "db_table": "accounts_company_membership",
                "ordering": ("company__name", "user__username"),
            },
        ),
        migrations.AddConstraint(
            model_name="companymembership",
            constraint=models.UniqueConstraint(
                fields=("company", "user"),
                name="accounts_unique_company_user_membership",
            ),
        ),
        migrations.AddConstraint(
            model_name="companymembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    role__in=[
                        "owner",
                        "operations-admin",
                        "inventory-manager",
                        "storekeeper",
                        "finance",
                        "internal-officer",
                        "rental-officer",
                        "reviewer",
                        "auditor",
                    ]
                ),
                name="accounts_membership_role_valid",
            ),
        ),
        migrations.AddIndex(
            model_name="companymembership",
            index=models.Index(
                fields=["company", "is_active", "role"],
                name="acct_member_company_role_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="companymembership",
            index=models.Index(
                fields=["user", "is_active"],
                name="acct_member_user_active_idx",
            ),
        ),
    ]
