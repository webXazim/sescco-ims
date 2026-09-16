from __future__ import annotations

import uuid

import django.db.models.deletion
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
]

ALL_PERMISSIONS = (
    "access.users.view", "access.users.manage", "access.profiles.view", "access.profiles.manage",
    "access.audit.view", "settings.view", "settings.manage", "shared.search.use",
    "shared.documents.view", "shared.documents.finalize", "shared.reports.view", "shared.reports.export",
    "shared.archive.view", "shared.archive.manage", "shared.trash.view", "shared.trash.manage",
    "inventory.dashboard.view", "inventory.stock.view", "inventory.stock.receive", "inventory.stock.issue",
    "inventory.stock.transfer", "inventory.stock.adjust", "inventory.movements.view", "inventory.movements.reverse",
    "inventory.projects.view", "inventory.projects.manage", "inventory.suppliers.view", "inventory.suppliers.manage",
    "inventory.locations.view", "inventory.locations.manage", "inventory.import.execute", "inventory.export.execute",
    "internal.overview.view", "internal.employees.view", "internal.employees.manage", "internal.organization.view",
    "internal.organization.manage", "internal.attendance.view", "internal.attendance.edit", "internal.attendance.submit",
    "internal.attendance.approve", "internal.salary_setup.view", "internal.salary_setup.manage", "internal.payroll_runs.view",
    "internal.payroll_runs.prepare", "internal.payroll_runs.approve", "internal.adjustments.view",
    "internal.adjustments.manage", "internal.adjustments.approve", "internal.payments.view", "internal.payments.prepare",
    "internal.payments.execute", "internal.wps.view", "internal.wps.export", "internal.documents.view",
    "internal.documents.finalize", "internal.reports.view", "internal.reports.export", "rental.overview.view",
    "rental.workers.view", "rental.workers.manage", "rental.suppliers.view", "rental.suppliers.manage",
    "rental.assignments.view", "rental.assignments.manage", "rental.timesheets.view", "rental.timesheets.edit",
    "rental.timesheets.submit", "rental.timesheets.approve", "rental.overtime.view", "rental.overtime.edit",
    "rental.overtime.submit", "rental.overtime.approve", "rental.adjustments.view", "rental.adjustments.manage",
    "rental.adjustments.approve", "rental.settlements.view", "rental.settlements.prepare", "rental.settlements.approve",
    "rental.payments.view", "rental.payments.prepare", "rental.payments.execute", "rental.documents.view",
    "rental.documents.finalize", "rental.reports.view", "rental.reports.export",
)

INVENTORY_VIEW = {
    "inventory.dashboard.view", "inventory.stock.view", "inventory.movements.view",
    "inventory.projects.view", "inventory.suppliers.view", "inventory.locations.view",
    "inventory.export.execute", "shared.search.use",
}
INVENTORY_EDIT = {"inventory.stock.receive", "inventory.stock.issue", "inventory.stock.transfer"}
INVENTORY_MANAGE = {
    "inventory.stock.adjust", "inventory.movements.reverse", "inventory.projects.manage",
    "inventory.suppliers.manage", "inventory.locations.manage", "shared.archive.view",
    "shared.archive.manage", "shared.trash.view", "shared.trash.manage",
}
INTERNAL_VIEW = {
    "internal.overview.view", "internal.employees.view", "internal.organization.view",
    "internal.attendance.view", "internal.salary_setup.view", "internal.payroll_runs.view",
    "internal.adjustments.view", "internal.payments.view", "internal.wps.view",
    "internal.documents.view", "internal.reports.view", "shared.documents.view",
    "shared.reports.view", "shared.search.use",
}
INTERNAL_EDIT = {
    "internal.employees.manage", "internal.organization.manage", "internal.attendance.edit",
    "internal.attendance.submit", "internal.salary_setup.manage", "internal.payroll_runs.prepare",
    "internal.adjustments.manage", "internal.payments.prepare", "internal.wps.export",
    "internal.documents.finalize", "internal.reports.export", "shared.documents.finalize",
    "shared.reports.export",
}
INTERNAL_APPROVE = {
    "internal.attendance.approve", "internal.payroll_runs.approve", "internal.adjustments.approve",
}
RENTAL_VIEW = {
    "rental.overview.view", "rental.workers.view", "rental.suppliers.view", "rental.assignments.view",
    "rental.timesheets.view", "rental.overtime.view", "rental.adjustments.view",
    "rental.settlements.view", "rental.payments.view", "rental.documents.view",
    "rental.reports.view", "shared.documents.view", "shared.reports.view", "shared.search.use",
}
RENTAL_EDIT = {
    "rental.workers.manage", "rental.suppliers.manage", "rental.assignments.manage",
    "rental.timesheets.edit", "rental.timesheets.submit", "rental.overtime.edit",
    "rental.overtime.submit", "rental.adjustments.manage", "rental.settlements.prepare",
    "rental.payments.prepare", "rental.documents.finalize", "rental.reports.export",
    "shared.documents.finalize", "shared.reports.export",
}
RENTAL_APPROVE = {
    "rental.timesheets.approve", "rental.overtime.approve", "rental.adjustments.approve",
    "rental.settlements.approve",
}

ROLE_LABELS = dict(ROLE_CHOICES)
ROLE_DESCRIPTIONS = {
    "owner": "Full company authority across Inventory, Internal Payroll, Rental Manpower, approvals, payments, settings, audit and access control.",
    "operations-admin": "Inventory and operational administration without automatic payroll, salary, approval, payment or access-management authority.",
    "access-admin": "User/access administration and access audit authority without automatic Inventory or Payroll operational access.",
    "inventory-manager": "Full Inventory operations, corrective actions and project/location administration.",
    "storekeeper": "Day-to-day stock entry, usage and transfer access without destructive corrective actions or administrative imports.",
    "finance": "Cross-payroll finance control, operational edits, approvals, payments, audit and access-policy visibility without Inventory mutation authority.",
    "internal-officer": "Internal employees, attendance, payroll preparation and bank/WPS setup only.",
    "rental-officer": "Rental workers, manpower suppliers, assignments, timesheets and settlement preparation only.",
    "reviewer": "Read across Payroll with controlled review/approval authority and no payments.",
    "auditor": "Read-only management and audit visibility with no operational changes.",
}


def permissions_for_role(role: str) -> set[str]:
    if role == "owner":
        return set(ALL_PERMISSIONS)
    if role == "operations-admin":
        return INVENTORY_VIEW | INVENTORY_EDIT | INVENTORY_MANAGE | {
            "inventory.import.execute", "settings.view", "settings.manage", "access.audit.view",
            "access.users.view", "access.profiles.view",
        }
    if role == "access-admin":
        return {
            "settings.view", "access.audit.view", "access.users.view", "access.users.manage",
            "access.profiles.view", "access.profiles.manage",
        }
    if role == "inventory-manager":
        return INVENTORY_VIEW | INVENTORY_EDIT | INVENTORY_MANAGE
    if role == "storekeeper":
        return INVENTORY_VIEW | INVENTORY_EDIT
    if role == "finance":
        return INTERNAL_VIEW | INTERNAL_EDIT | INTERNAL_APPROVE | {"internal.payments.execute"} | \
            RENTAL_VIEW | RENTAL_EDIT | RENTAL_APPROVE | {"rental.payments.execute"} | {
                "settings.view", "access.audit.view", "access.users.view", "access.profiles.view",
            }
    if role == "internal-officer":
        return INTERNAL_VIEW | INTERNAL_EDIT
    if role == "rental-officer":
        return RENTAL_VIEW | RENTAL_EDIT
    if role == "reviewer":
        return INTERNAL_VIEW | INTERNAL_APPROVE | RENTAL_VIEW | RENTAL_APPROVE | {
            "settings.view", "access.audit.view",
        }
    if role == "auditor":
        return {"settings.view", "access.audit.view"}
    raise RuntimeError(f"Unknown company access role during 1.0.88 backfill: {role}")


def profile_key(role: str) -> str:
    return f"role-{role}"


def backfill_access_profiles(apps, schema_editor):
    db = schema_editor.connection.alias
    Company = apps.get_model("core", "Company")
    AccessProfile = apps.get_model("accounts", "AccessProfile")
    AccessProfilePermission = apps.get_model("accounts", "AccessProfilePermission")
    CompanyMembership = apps.get_model("accounts", "CompanyMembership")

    profile_by_company_role: dict[tuple[object, str], object] = {}
    for company_id in Company.objects.using(db).values_list("id", flat=True).iterator():
        for role, label in ROLE_CHOICES:
            profile, _created = AccessProfile.objects.using(db).get_or_create(
                company_id=company_id,
                key=profile_key(role),
                defaults={
                    "name": label,
                    "description": ROLE_DESCRIPTIONS[role],
                    "is_system": True,
                    "is_active": True,
                },
            )
            desired = sorted(permissions_for_role(role))
            existing = set(
                AccessProfilePermission.objects.using(db)
                .filter(profile_id=profile.pk)
                .values_list("permission", flat=True)
            )
            rows = [
                AccessProfilePermission(profile_id=profile.pk, permission=permission)
                for permission in desired
                if permission not in existing
            ]
            if rows:
                AccessProfilePermission.objects.using(db).bulk_create(rows, batch_size=250)
            profile_by_company_role[(company_id, role)] = profile.pk

    batch = []
    for membership in CompanyMembership.objects.using(db).filter(access_profile__isnull=True).iterator(chunk_size=500):
        membership.access_profile_id = profile_by_company_role[(membership.company_id, membership.role)]
        batch.append(membership)
        if len(batch) >= 500:
            CompanyMembership.objects.using(db).bulk_update(batch, ["access_profile"], batch_size=500)
            batch = []
    if batch:
        CompanyMembership.objects.using(db).bulk_update(batch, ["access_profile"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_backfill_initial_company_access"),
        ("projects", "0006_project_reversible_archive_state"),
        ("inventory", "0014_inventory_master_lifecycle"),
        ("internal_payroll", "0013_postgres_search_query_hardening"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccessProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("key", models.SlugField(max_length=80)),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True)),
                ("is_system", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="access_profiles", to="core.company")),
            ],
            options={
                "db_table": "accounts_access_profile",
                "ordering": ("company__name", "name", "key"),
            },
        ),
        migrations.AddConstraint(
            model_name="accessprofile",
            constraint=models.UniqueConstraint(fields=("company", "key"), name="accounts_profile_company_key_uniq"),
        ),
        migrations.AddIndex(
            model_name="accessprofile",
            index=models.Index(fields=["company", "is_active", "name"], name="acct_profile_company_active_idx"),
        ),
        migrations.CreateModel(
            name="AccessProfilePermission",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("permission", models.CharField(max_length=96)),
                ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="permission_grants", to="accounts.accessprofile")),
            ],
            options={"db_table": "accounts_access_profile_permission", "ordering": ("profile__name", "permission")},
        ),
        migrations.AddConstraint(
            model_name="accessprofilepermission",
            constraint=models.UniqueConstraint(fields=("profile", "permission"), name="accounts_profile_permission_uniq"),
        ),
        migrations.AddConstraint(
            model_name="accessprofilepermission",
            constraint=models.CheckConstraint(condition=models.Q(permission__in=ALL_PERMISSIONS), name="accounts_profile_permission_valid"),
        ),
        migrations.AddIndex(
            model_name="accessprofilepermission",
            index=models.Index(fields=["profile", "permission"], name="acct_profile_permission_idx"),
        ),
        migrations.AddField(
            model_name="companymembership",
            name="access_profile",
            field=models.ForeignKey(blank=True, help_text="Granular access authority. 1.0.88 keeps role as a compatibility bridge.", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="memberships", to="accounts.accessprofile"),
        ),
        migrations.AddField(
            model_name="companymembership",
            name="branch_scope_mode",
            field=models.CharField(choices=[("all", "All company records"), ("selected", "Selected records only"), ("none", "No records")], default="all", max_length=12),
        ),
        migrations.AddField(
            model_name="companymembership",
            name="inventory_location_scope_mode",
            field=models.CharField(choices=[("all", "All company records"), ("selected", "Selected records only"), ("none", "No records")], default="all", max_length=12),
        ),
        migrations.AddField(
            model_name="companymembership",
            name="project_scope_mode",
            field=models.CharField(choices=[("all", "All company records"), ("selected", "Selected records only"), ("none", "No records")], default="all", max_length=12),
        ),
        migrations.CreateModel(
            name="MembershipProjectScope",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_scopes", to="accounts.companymembership")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="access_membership_scopes", to="projects.project")),
            ],
            options={"db_table": "accounts_membership_project_scope"},
        ),
        migrations.AddConstraint(
            model_name="membershipprojectscope",
            constraint=models.UniqueConstraint(fields=("membership", "project"), name="accounts_member_project_scope_uniq"),
        ),
        migrations.AddIndex(
            model_name="membershipprojectscope",
            index=models.Index(fields=["membership", "project"], name="acct_member_project_scope_idx"),
        ),
        migrations.CreateModel(
            name="MembershipBranchScope",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="access_membership_scopes", to="internal_payroll.branch")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="branch_scopes", to="accounts.companymembership")),
            ],
            options={"db_table": "accounts_membership_branch_scope"},
        ),
        migrations.AddConstraint(
            model_name="membershipbranchscope",
            constraint=models.UniqueConstraint(fields=("membership", "branch"), name="accounts_member_branch_scope_uniq"),
        ),
        migrations.AddIndex(
            model_name="membershipbranchscope",
            index=models.Index(fields=["membership", "branch"], name="acct_member_branch_scope_idx"),
        ),
        migrations.CreateModel(
            name="MembershipInventoryLocationScope",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("inventory_location", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="access_membership_scopes", to="inventory.inventorylocation")),
                ("membership", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="inventory_location_scopes", to="accounts.companymembership")),
            ],
            options={"db_table": "accounts_membership_inventory_location_scope"},
        ),
        migrations.AddConstraint(
            model_name="membershipinventorylocationscope",
            constraint=models.UniqueConstraint(fields=("membership", "inventory_location"), name="accounts_member_inventory_location_scope_uniq"),
        ),
        migrations.AddIndex(
            model_name="membershipinventorylocationscope",
            index=models.Index(fields=["membership", "inventory_location"], name="acct_member_location_scope_idx"),
        ),
        migrations.RemoveConstraint(model_name="companymembership", name="accounts_membership_role_valid"),
        migrations.AlterField(model_name="companymembership", name="role", field=models.CharField(choices=ROLE_CHOICES, max_length=32)),
        migrations.AddConstraint(
            model_name="companymembership",
            constraint=models.CheckConstraint(condition=models.Q(role__in=[value for value, _label in ROLE_CHOICES]), name="accounts_membership_role_valid"),
        ),
        migrations.RunPython(backfill_access_profiles, migrations.RunPython.noop),
    ]
