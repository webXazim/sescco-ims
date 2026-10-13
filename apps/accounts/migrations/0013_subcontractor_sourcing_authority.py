"""Add independent Subcontractor View/Edit Access Profile permissions.

Staging-only pending re-certification of the frozen v1.0.117 access catalog.
"""
from django.db import migrations, models

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


def grant_company_owner(apps, schema_editor):
    Profile = apps.get_model('accounts', 'AccessProfile')
    Grant = apps.get_model('accounts', 'AccessProfilePermission')
    for profile in Profile.objects.filter(key='role-owner', is_system=True).iterator():
        for permission in ('sourcing.subcontractors.view', 'sourcing.subcontractors.manage'):
            Grant.objects.get_or_create(profile_id=profile.pk, permission=permission)


def noop_reverse(apps, schema_editor):
    # Do not silently revoke assigned permissions on rollback.
    pass


class Migration(migrations.Migration):
    dependencies = [('accounts', '0012_sourcing_access_control_authority')]
    operations = [
        migrations.RemoveConstraint(model_name='accessprofilepermission', name='accounts_profile_permission_valid'),
        migrations.AddConstraint(
            model_name='accessprofilepermission',
            constraint=models.CheckConstraint(
                condition=models.Q(permission__in=ALL_PERMISSIONS), name='accounts_profile_permission_valid',
            ),
        ),
        migrations.RunPython(grant_company_owner, noop_reverse),
    ]
