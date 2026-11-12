from django.db import migrations, models

ROLE_CHOICES = [
    ("owner", "Company Owner"), ("operations-admin", "Operations Administrator"),
    ("access-admin", "Access Administrator"), ("inventory-manager", "Inventory Manager"),
    ("project-manager", "Project Manager"), ("storekeeper", "Storekeeper"),
    ("finance", "Finance Manager"), ("internal-officer", "Internal Payroll Officer"),
    ("rental-officer", "Rental Manpower Officer"), ("rental-supervisor", "Rental Supervisor / Foreman"),
    ("reviewer", "Finance Reviewer"), ("auditor", "Read-only Auditor"),
    ("custom", "Custom Access Profile"),
]

ALL_PERMISSIONS = (
    'access.users.view',
    'access.users.manage',
    'access.profiles.view',
    'access.profiles.manage',
    'access.audit.view',
    'settings.view',
    'settings.manage',
    'shared.search.use',
    'shared.documents.view',
    'shared.documents.finalize',
    'shared.reports.view',
    'shared.reports.export',
    'shared.archive.view',
    'shared.archive.manage',
    'shared.trash.view',
    'shared.trash.manage',
    'inventory.dashboard.view',
    'inventory.stock.view',
    'inventory.stock.receive',
    'inventory.stock.issue',
    'inventory.stock.transfer',
    'inventory.stock.approve',
    'inventory.stock.adjust',
    'inventory.movements.view',
    'inventory.movements.reverse',
    'inventory.projects.view',
    'inventory.projects.manage',
    'inventory.suppliers.view',
    'inventory.suppliers.manage',
    'inventory.locations.view',
    'inventory.locations.manage',
    'inventory.import.execute',
    'inventory.export.execute',
    'internal.overview.view',
    'internal.employees.view',
    'internal.employees.manage',
    'internal.organization.view',
    'internal.organization.manage',
    'internal.attendance.view',
    'internal.attendance.edit',
    'internal.attendance.submit',
    'internal.attendance.approve',
    'internal.salary_setup.view',
    'internal.salary_setup.manage',
    'internal.payroll_runs.view',
    'internal.payroll_runs.prepare',
    'internal.payroll_runs.review',
    'internal.payroll_runs.approve',
    'internal.adjustments.view',
    'internal.adjustments.manage',
    'internal.adjustments.approve',
    'internal.payments.view',
    'internal.payments.prepare',
    'internal.payments.execute',
    'internal.wps.view',
    'internal.wps.export',
    'internal.documents.view',
    'internal.documents.finalize',
    'internal.reports.view',
    'internal.reports.export',
    'rental.overview.view',
    'rental.workers.view',
    'rental.workers.manage',
    'rental.suppliers.view',
    'rental.suppliers.manage',
    'rental.assignments.view',
    'rental.assignments.manage',
    'rental.timesheets.view',
    'rental.timesheets.edit',
    'rental.timesheets.submit',
    'rental.timesheets.approve',
    'rental.overtime.view',
    'rental.overtime.edit',
    'rental.overtime.submit',
    'rental.overtime.approve',
    'rental.adjustments.view',
    'rental.adjustments.manage',
    'rental.adjustments.approve',
    'rental.settlements.view',
    'rental.settlements.prepare',
    'rental.settlements.approve',
    'rental.payments.view',
    'rental.payments.prepare',
    'rental.payments.execute',
    'rental.documents.view',
    'rental.documents.finalize',
    'rental.reports.view',
    'rental.reports.export',
    'sourcing.vendors.view',
    'sourcing.vendors.manage',
    'sourcing.manpower.view',
    'sourcing.manpower.manage',
    'sourcing.masters.view',
    'sourcing.masters.manage',
    'sourcing.export.execute',
    'sourcing.subcontractors.view',
    'sourcing.subcontractors.manage',
)

MANAGER_PERMISSIONS = (
    "inventory.dashboard.view", "inventory.stock.view", "inventory.movements.view",
    "inventory.projects.view", "inventory.locations.view", "inventory.stock.approve",
)

def seed_project_manager(apps, schema_editor):
    Company = apps.get_model("core", "Company")
    Profile = apps.get_model("accounts", "AccessProfile")
    Grant = apps.get_model("accounts", "AccessProfilePermission")
    db = schema_editor.connection.alias
    for company in Company.objects.using(db).all().iterator():
        profile, _ = Profile.objects.using(db).get_or_create(
            company=company, key="role-project-manager", defaults={
                "name": "Project Manager", "description": "Assigned project inventory review and approval only.",
                "is_system": True, "is_active": True,
            },
        )
        for permission in MANAGER_PERMISSIONS:
            Grant.objects.using(db).get_or_create(profile=profile, permission=permission)
    for profile in Profile.objects.using(db).filter(key="role-owner", is_system=True).iterator():
        Grant.objects.using(db).get_or_create(profile=profile, permission="inventory.stock.approve")

class Migration(migrations.Migration):
    dependencies = [("accounts", "0015_merge_subcontractor_authority")]
    operations = [
        migrations.RemoveConstraint(model_name="companymembership", name="accounts_membership_role_valid"),
        migrations.AlterField(model_name="companymembership", name="role", field=models.CharField(
            max_length=32, choices=ROLE_CHOICES,
            help_text="Compatibility classification only; AccessProfile is the authorization authority.",
        )),
        migrations.AddConstraint(model_name="companymembership", constraint=models.CheckConstraint(
            condition=models.Q(role__in=[value for value, _ in ROLE_CHOICES]),
            name="accounts_membership_role_valid",
        )),
        # The persisted AccessProfilePermission DB CHECK from 0013 must admit
        # the new permission before migration seeds project-manager grants.
        migrations.RemoveConstraint(model_name="accessprofilepermission", name="accounts_profile_permission_valid"),
        migrations.AddConstraint(model_name="accessprofilepermission", constraint=models.CheckConstraint(
            condition=models.Q(permission__in=ALL_PERMISSIONS), name="accounts_profile_permission_valid",
        )),
        migrations.RunPython(seed_project_manager, migrations.RunPython.noop),
    ]
