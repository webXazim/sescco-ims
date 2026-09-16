from __future__ import annotations

from enum import StrEnum

from .roles import AccessRole, Capability, Workspace, role_definition


class AccessPermission(StrEnum):
    # Administration / shared platform authority.
    ACCESS_USERS_VIEW = "access.users.view"
    ACCESS_USERS_MANAGE = "access.users.manage"
    ACCESS_PROFILES_VIEW = "access.profiles.view"
    ACCESS_PROFILES_MANAGE = "access.profiles.manage"
    ACCESS_AUDIT_VIEW = "access.audit.view"
    SETTINGS_VIEW = "settings.view"
    SETTINGS_MANAGE = "settings.manage"
    SHARED_SEARCH_USE = "shared.search.use"
    SHARED_DOCUMENTS_VIEW = "shared.documents.view"
    SHARED_DOCUMENTS_FINALIZE = "shared.documents.finalize"
    SHARED_REPORTS_VIEW = "shared.reports.view"
    SHARED_REPORTS_EXPORT = "shared.reports.export"
    SHARED_ARCHIVE_VIEW = "shared.archive.view"
    SHARED_ARCHIVE_MANAGE = "shared.archive.manage"
    SHARED_TRASH_VIEW = "shared.trash.view"
    SHARED_TRASH_MANAGE = "shared.trash.manage"

    # Inventory.
    INVENTORY_DASHBOARD_VIEW = "inventory.dashboard.view"
    INVENTORY_STOCK_VIEW = "inventory.stock.view"
    INVENTORY_STOCK_RECEIVE = "inventory.stock.receive"
    INVENTORY_STOCK_ISSUE = "inventory.stock.issue"
    INVENTORY_STOCK_TRANSFER = "inventory.stock.transfer"
    INVENTORY_STOCK_ADJUST = "inventory.stock.adjust"
    INVENTORY_MOVEMENTS_VIEW = "inventory.movements.view"
    INVENTORY_MOVEMENTS_REVERSE = "inventory.movements.reverse"
    INVENTORY_PROJECTS_VIEW = "inventory.projects.view"
    INVENTORY_PROJECTS_MANAGE = "inventory.projects.manage"
    INVENTORY_SUPPLIERS_VIEW = "inventory.suppliers.view"
    INVENTORY_SUPPLIERS_MANAGE = "inventory.suppliers.manage"
    INVENTORY_LOCATIONS_VIEW = "inventory.locations.view"
    INVENTORY_LOCATIONS_MANAGE = "inventory.locations.manage"
    INVENTORY_IMPORT_EXECUTE = "inventory.import.execute"
    INVENTORY_EXPORT_EXECUTE = "inventory.export.execute"

    # Internal Company Payroll.
    INTERNAL_OVERVIEW_VIEW = "internal.overview.view"
    INTERNAL_EMPLOYEES_VIEW = "internal.employees.view"
    INTERNAL_EMPLOYEES_MANAGE = "internal.employees.manage"
    INTERNAL_ORGANIZATION_VIEW = "internal.organization.view"
    INTERNAL_ORGANIZATION_MANAGE = "internal.organization.manage"
    INTERNAL_ATTENDANCE_VIEW = "internal.attendance.view"
    INTERNAL_ATTENDANCE_EDIT = "internal.attendance.edit"
    INTERNAL_ATTENDANCE_SUBMIT = "internal.attendance.submit"
    INTERNAL_ATTENDANCE_APPROVE = "internal.attendance.approve"
    INTERNAL_SALARY_SETUP_VIEW = "internal.salary_setup.view"
    INTERNAL_SALARY_SETUP_MANAGE = "internal.salary_setup.manage"
    INTERNAL_PAYROLL_RUNS_VIEW = "internal.payroll_runs.view"
    INTERNAL_PAYROLL_RUNS_PREPARE = "internal.payroll_runs.prepare"
    INTERNAL_PAYROLL_RUNS_REVIEW = "internal.payroll_runs.review"
    INTERNAL_PAYROLL_RUNS_APPROVE = "internal.payroll_runs.approve"
    INTERNAL_ADJUSTMENTS_VIEW = "internal.adjustments.view"
    INTERNAL_ADJUSTMENTS_MANAGE = "internal.adjustments.manage"
    INTERNAL_ADJUSTMENTS_APPROVE = "internal.adjustments.approve"
    INTERNAL_PAYMENTS_VIEW = "internal.payments.view"
    INTERNAL_PAYMENTS_PREPARE = "internal.payments.prepare"
    INTERNAL_PAYMENTS_EXECUTE = "internal.payments.execute"
    INTERNAL_WPS_VIEW = "internal.wps.view"
    INTERNAL_WPS_EXPORT = "internal.wps.export"
    INTERNAL_DOCUMENTS_VIEW = "internal.documents.view"
    INTERNAL_DOCUMENTS_FINALIZE = "internal.documents.finalize"
    INTERNAL_REPORTS_VIEW = "internal.reports.view"
    INTERNAL_REPORTS_EXPORT = "internal.reports.export"

    # Rental Manpower.
    RENTAL_OVERVIEW_VIEW = "rental.overview.view"
    RENTAL_WORKERS_VIEW = "rental.workers.view"
    RENTAL_WORKERS_MANAGE = "rental.workers.manage"
    RENTAL_SUPPLIERS_VIEW = "rental.suppliers.view"
    RENTAL_SUPPLIERS_MANAGE = "rental.suppliers.manage"
    RENTAL_ASSIGNMENTS_VIEW = "rental.assignments.view"
    RENTAL_ASSIGNMENTS_MANAGE = "rental.assignments.manage"
    RENTAL_TIMESHEETS_VIEW = "rental.timesheets.view"
    RENTAL_TIMESHEETS_EDIT = "rental.timesheets.edit"
    RENTAL_TIMESHEETS_SUBMIT = "rental.timesheets.submit"
    RENTAL_TIMESHEETS_APPROVE = "rental.timesheets.approve"
    RENTAL_OVERTIME_VIEW = "rental.overtime.view"
    RENTAL_OVERTIME_EDIT = "rental.overtime.edit"
    RENTAL_OVERTIME_SUBMIT = "rental.overtime.submit"
    RENTAL_OVERTIME_APPROVE = "rental.overtime.approve"
    RENTAL_ADJUSTMENTS_VIEW = "rental.adjustments.view"
    RENTAL_ADJUSTMENTS_MANAGE = "rental.adjustments.manage"
    RENTAL_ADJUSTMENTS_APPROVE = "rental.adjustments.approve"
    RENTAL_SETTLEMENTS_VIEW = "rental.settlements.view"
    RENTAL_SETTLEMENTS_PREPARE = "rental.settlements.prepare"
    RENTAL_SETTLEMENTS_APPROVE = "rental.settlements.approve"
    RENTAL_PAYMENTS_VIEW = "rental.payments.view"
    RENTAL_PAYMENTS_PREPARE = "rental.payments.prepare"
    RENTAL_PAYMENTS_EXECUTE = "rental.payments.execute"
    RENTAL_DOCUMENTS_VIEW = "rental.documents.view"
    RENTAL_DOCUMENTS_FINALIZE = "rental.documents.finalize"
    RENTAL_REPORTS_VIEW = "rental.reports.view"
    RENTAL_REPORTS_EXPORT = "rental.reports.export"

    # Reference-only Sourcing Directory. These permissions never imply Inventory,
    # Payroll, Projects, Documents or Accounting authority.
    SOURCING_VENDORS_VIEW = "sourcing.vendors.view"
    SOURCING_VENDORS_MANAGE = "sourcing.vendors.manage"
    SOURCING_MANPOWER_VIEW = "sourcing.manpower.view"
    SOURCING_MANPOWER_MANAGE = "sourcing.manpower.manage"
    SOURCING_MASTERS_VIEW = "sourcing.masters.view"
    SOURCING_MASTERS_MANAGE = "sourcing.masters.manage"
    SOURCING_EXPORT_EXECUTE = "sourcing.export.execute"


_PERMISSION_LABELS: dict[AccessPermission, str] = {
    permission: permission.value.replace(".", " · ").replace("_", " ").title()
    for permission in AccessPermission
}
_PERMISSION_LABELS.update({
    AccessPermission.SOURCING_VENDORS_VIEW: "Vendor Sourcing · View",
    AccessPermission.SOURCING_VENDORS_MANAGE: "Vendor Sourcing · Edit",
    AccessPermission.SOURCING_MANPOWER_VIEW: "Manpower Sourcing · View",
    AccessPermission.SOURCING_MANPOWER_MANAGE: "Manpower Sourcing · Edit",
    AccessPermission.SOURCING_MASTERS_VIEW: "Sourcing Reference Masters · View",
    AccessPermission.SOURCING_MASTERS_MANAGE: "Sourcing Reference Masters · Edit",
    AccessPermission.SOURCING_EXPORT_EXECUTE: "Sourcing Directory · Export",
})


def access_permission_choices() -> tuple[tuple[str, str], ...]:
    return tuple((permission.value, _PERMISSION_LABELS[permission]) for permission in AccessPermission)


INVENTORY_VIEW_PERMISSIONS = frozenset({
    AccessPermission.INVENTORY_DASHBOARD_VIEW,
    AccessPermission.INVENTORY_STOCK_VIEW,
    AccessPermission.INVENTORY_MOVEMENTS_VIEW,
    AccessPermission.INVENTORY_PROJECTS_VIEW,
    AccessPermission.INVENTORY_SUPPLIERS_VIEW,
    AccessPermission.INVENTORY_LOCATIONS_VIEW,
    AccessPermission.INVENTORY_EXPORT_EXECUTE,
    AccessPermission.SHARED_SEARCH_USE,
})
INVENTORY_EDIT_PERMISSIONS = frozenset({
    AccessPermission.INVENTORY_STOCK_RECEIVE,
    AccessPermission.INVENTORY_STOCK_ISSUE,
    AccessPermission.INVENTORY_STOCK_TRANSFER,
})
INVENTORY_MANAGE_PERMISSIONS = frozenset({
    AccessPermission.INVENTORY_STOCK_ADJUST,
    AccessPermission.INVENTORY_MOVEMENTS_REVERSE,
    AccessPermission.INVENTORY_PROJECTS_MANAGE,
    AccessPermission.INVENTORY_SUPPLIERS_MANAGE,
    AccessPermission.INVENTORY_LOCATIONS_MANAGE,
    AccessPermission.SHARED_ARCHIVE_VIEW,
    AccessPermission.SHARED_ARCHIVE_MANAGE,
    AccessPermission.SHARED_TRASH_VIEW,
    AccessPermission.SHARED_TRASH_MANAGE,
})

INTERNAL_VIEW_PERMISSIONS = frozenset({
    AccessPermission.INTERNAL_OVERVIEW_VIEW,
    AccessPermission.INTERNAL_EMPLOYEES_VIEW,
    AccessPermission.INTERNAL_ORGANIZATION_VIEW,
    AccessPermission.INTERNAL_ATTENDANCE_VIEW,
    AccessPermission.INTERNAL_SALARY_SETUP_VIEW,
    AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW,
    AccessPermission.INTERNAL_ADJUSTMENTS_VIEW,
    AccessPermission.INTERNAL_PAYMENTS_VIEW,
    AccessPermission.INTERNAL_WPS_VIEW,
    AccessPermission.INTERNAL_DOCUMENTS_VIEW,
    AccessPermission.INTERNAL_REPORTS_VIEW,
    AccessPermission.SHARED_DOCUMENTS_VIEW,
    AccessPermission.SHARED_REPORTS_VIEW,
    AccessPermission.SHARED_SEARCH_USE,
})
INTERNAL_EDIT_PERMISSIONS = frozenset({
    AccessPermission.INTERNAL_EMPLOYEES_MANAGE,
    AccessPermission.INTERNAL_ORGANIZATION_MANAGE,
    AccessPermission.INTERNAL_ATTENDANCE_EDIT,
    AccessPermission.INTERNAL_ATTENDANCE_SUBMIT,
    AccessPermission.INTERNAL_SALARY_SETUP_MANAGE,
    AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE,
    AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE,
    AccessPermission.INTERNAL_PAYMENTS_PREPARE,
    AccessPermission.INTERNAL_WPS_EXPORT,
    AccessPermission.INTERNAL_DOCUMENTS_FINALIZE,
    AccessPermission.INTERNAL_REPORTS_EXPORT,
    AccessPermission.SHARED_DOCUMENTS_FINALIZE,
    AccessPermission.SHARED_REPORTS_EXPORT,
})
INTERNAL_REVIEW_PERMISSIONS = frozenset({AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW})
INTERNAL_APPROVE_PERMISSIONS = frozenset({
    AccessPermission.INTERNAL_ATTENDANCE_APPROVE,
    AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE,
    AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE,
})
INTERNAL_PAY_PERMISSIONS = frozenset({AccessPermission.INTERNAL_PAYMENTS_EXECUTE})

RENTAL_VIEW_PERMISSIONS = frozenset({
    AccessPermission.RENTAL_OVERVIEW_VIEW,
    AccessPermission.RENTAL_WORKERS_VIEW,
    AccessPermission.RENTAL_SUPPLIERS_VIEW,
    AccessPermission.RENTAL_ASSIGNMENTS_VIEW,
    AccessPermission.RENTAL_TIMESHEETS_VIEW,
    AccessPermission.RENTAL_OVERTIME_VIEW,
    AccessPermission.RENTAL_ADJUSTMENTS_VIEW,
    AccessPermission.RENTAL_SETTLEMENTS_VIEW,
    AccessPermission.RENTAL_PAYMENTS_VIEW,
    AccessPermission.RENTAL_DOCUMENTS_VIEW,
    AccessPermission.RENTAL_REPORTS_VIEW,
    AccessPermission.SHARED_DOCUMENTS_VIEW,
    AccessPermission.SHARED_REPORTS_VIEW,
    AccessPermission.SHARED_SEARCH_USE,
})
RENTAL_EDIT_PERMISSIONS = frozenset({
    AccessPermission.RENTAL_WORKERS_MANAGE,
    AccessPermission.RENTAL_SUPPLIERS_MANAGE,
    AccessPermission.RENTAL_ASSIGNMENTS_MANAGE,
    AccessPermission.RENTAL_TIMESHEETS_EDIT,
    AccessPermission.RENTAL_TIMESHEETS_SUBMIT,
    AccessPermission.RENTAL_OVERTIME_EDIT,
    AccessPermission.RENTAL_OVERTIME_SUBMIT,
    AccessPermission.RENTAL_ADJUSTMENTS_MANAGE,
    AccessPermission.RENTAL_SETTLEMENTS_PREPARE,
    AccessPermission.RENTAL_PAYMENTS_PREPARE,
    AccessPermission.RENTAL_DOCUMENTS_FINALIZE,
    AccessPermission.RENTAL_REPORTS_EXPORT,
    AccessPermission.SHARED_DOCUMENTS_FINALIZE,
    AccessPermission.SHARED_REPORTS_EXPORT,
})
RENTAL_APPROVE_PERMISSIONS = frozenset({
    AccessPermission.RENTAL_TIMESHEETS_APPROVE,
    AccessPermission.RENTAL_OVERTIME_APPROVE,
    AccessPermission.RENTAL_ADJUSTMENTS_APPROVE,
    AccessPermission.RENTAL_SETTLEMENTS_APPROVE,
})
RENTAL_PAY_PERMISSIONS = frozenset({AccessPermission.RENTAL_PAYMENTS_EXECUTE})

# Sourcing is a separate reference-only module. No operational role inherits these
# sets. Owner receives them only because OWNER returns the complete AccessPermission
# enum; administrators can assign any subset through custom Access Profiles.
SOURCING_VENDOR_VIEW_PERMISSIONS = frozenset({AccessPermission.SOURCING_VENDORS_VIEW})
SOURCING_VENDOR_EDIT_PERMISSIONS = frozenset({AccessPermission.SOURCING_VENDORS_MANAGE})
SOURCING_MANPOWER_VIEW_PERMISSIONS = frozenset({AccessPermission.SOURCING_MANPOWER_VIEW})
SOURCING_MANPOWER_EDIT_PERMISSIONS = frozenset({AccessPermission.SOURCING_MANPOWER_MANAGE})
SOURCING_MASTER_VIEW_PERMISSIONS = frozenset({AccessPermission.SOURCING_MASTERS_VIEW})
SOURCING_MASTER_EDIT_PERMISSIONS = frozenset({AccessPermission.SOURCING_MASTERS_MANAGE})
SOURCING_MODULE_PERMISSIONS = frozenset({
    AccessPermission.SOURCING_VENDORS_VIEW,
    AccessPermission.SOURCING_VENDORS_MANAGE,
    AccessPermission.SOURCING_MANPOWER_VIEW,
    AccessPermission.SOURCING_MANPOWER_MANAGE,
    AccessPermission.SOURCING_MASTERS_VIEW,
    AccessPermission.SOURCING_MASTERS_MANAGE,
    AccessPermission.SOURCING_EXPORT_EXECUTE,
})


def permissions_for_legacy_role(role: str) -> frozenset[AccessPermission]:
    """Build the permission set for one built-in system profile template.

    From 1.0.89 onward this mapping is provisioning/migration metadata only. Runtime
    authorization reads the persisted AccessProfile grants through EffectiveAccess.
    """

    definition = role_definition(role)

    # 1.0.95 freezes Internal Payroll / Finance duties as explicit permission
    # sets instead of inheriting the broad EDIT_INTERNAL / APPROVE / PAY bundles.
    # This keeps employee/attendance preparation, finance review, final approval,
    # Bank/WPS preparation and payment execution independently assignable.
    if role == AccessRole.INTERNAL_PAYROLL_OFFICER:
        return frozenset({
            *INTERNAL_VIEW_PERMISSIONS,
            AccessPermission.INTERNAL_EMPLOYEES_MANAGE,
            AccessPermission.INTERNAL_ORGANIZATION_MANAGE,
            AccessPermission.INTERNAL_ATTENDANCE_EDIT,
            AccessPermission.INTERNAL_ATTENDANCE_SUBMIT,
            AccessPermission.INTERNAL_SALARY_SETUP_MANAGE,
            AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE,
            AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE,
            AccessPermission.INTERNAL_PAYMENTS_PREPARE,
            AccessPermission.INTERNAL_WPS_EXPORT,
            AccessPermission.INTERNAL_DOCUMENTS_FINALIZE,
            AccessPermission.INTERNAL_REPORTS_EXPORT,
            AccessPermission.SHARED_DOCUMENTS_FINALIZE,
            AccessPermission.SHARED_REPORTS_EXPORT,
        })

    if role == AccessRole.FINANCE_REVIEWER:
        return frozenset({
            *INTERNAL_VIEW_PERMISSIONS,
            AccessPermission.INTERNAL_ATTENDANCE_APPROVE,
            AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE,
            AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW,
            *RENTAL_VIEW_PERMISSIONS,
            *RENTAL_APPROVE_PERMISSIONS,
            AccessPermission.SETTINGS_VIEW,
            AccessPermission.ACCESS_AUDIT_VIEW,
        })

    if role == AccessRole.FINANCE_MANAGER:
        return frozenset({
            *INTERNAL_VIEW_PERMISSIONS,
            AccessPermission.INTERNAL_ATTENDANCE_APPROVE,
            AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE,
            AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE,
            AccessPermission.INTERNAL_PAYMENTS_PREPARE,
            AccessPermission.INTERNAL_PAYMENTS_EXECUTE,
            AccessPermission.INTERNAL_WPS_EXPORT,
            AccessPermission.INTERNAL_DOCUMENTS_FINALIZE,
            AccessPermission.INTERNAL_REPORTS_EXPORT,
            AccessPermission.SHARED_DOCUMENTS_FINALIZE,
            AccessPermission.SHARED_REPORTS_EXPORT,
            *RENTAL_VIEW_PERMISSIONS,
            *RENTAL_EDIT_PERMISSIONS,
            *RENTAL_APPROVE_PERMISSIONS,
            AccessPermission.RENTAL_PAYMENTS_EXECUTE,
            AccessPermission.SETTINGS_VIEW,
            AccessPermission.ACCESS_AUDIT_VIEW,
            AccessPermission.ACCESS_USERS_VIEW,
            AccessPermission.ACCESS_PROFILES_VIEW,
        })

    # 1.0.93 freezes Storekeeper as a narrow scoped operational profile. Do not
    # derive it from broader Inventory capabilities: Storekeepers can receive, issue
    # and transfer stock inside their assigned Project/Location scope, but cannot
    # adjust/reverse, import, administer masters, or manage Archive/Trash lifecycle.
    if role == AccessRole.STOREKEEPER:
        return frozenset({
            AccessPermission.INVENTORY_DASHBOARD_VIEW,
            AccessPermission.INVENTORY_STOCK_VIEW,
            AccessPermission.INVENTORY_STOCK_RECEIVE,
            AccessPermission.INVENTORY_STOCK_ISSUE,
            AccessPermission.INVENTORY_STOCK_TRANSFER,
            AccessPermission.INVENTORY_MOVEMENTS_VIEW,
            AccessPermission.INVENTORY_PROJECTS_VIEW,
            AccessPermission.INVENTORY_SUPPLIERS_VIEW,
            AccessPermission.INVENTORY_LOCATIONS_VIEW,
            AccessPermission.INVENTORY_EXPORT_EXECUTE,
            AccessPermission.SHARED_SEARCH_USE,
        })

    # 1.0.92 deliberately provisions the Rental Supervisor / Foreman as a narrow
    # operational profile. Do not derive this profile from EDIT_RENTAL: doing so would
    # grant supplier, settlement, payment, document and lifecycle authority.
    if role == AccessRole.RENTAL_SUPERVISOR:
        return frozenset({
            AccessPermission.RENTAL_OVERVIEW_VIEW,
            AccessPermission.RENTAL_WORKERS_VIEW,
            AccessPermission.RENTAL_ASSIGNMENTS_VIEW,
            AccessPermission.RENTAL_TIMESHEETS_VIEW,
            AccessPermission.RENTAL_TIMESHEETS_EDIT,
            AccessPermission.RENTAL_TIMESHEETS_SUBMIT,
            AccessPermission.RENTAL_OVERTIME_VIEW,
            AccessPermission.RENTAL_OVERTIME_EDIT,
            AccessPermission.RENTAL_OVERTIME_SUBMIT,
        })

    permissions: set[AccessPermission] = set()

    if Workspace.INVENTORY in definition.workspaces:
        permissions.update(INVENTORY_VIEW_PERMISSIONS)
    if Capability.EDIT_INVENTORY in definition.capabilities:
        permissions.update(INVENTORY_EDIT_PERMISSIONS)
    if Capability.MANAGE_INVENTORY in definition.capabilities:
        permissions.update(INVENTORY_MANAGE_PERMISSIONS)
    if Capability.IMPORT_INVENTORY in definition.capabilities:
        permissions.add(AccessPermission.INVENTORY_IMPORT_EXECUTE)

    if Workspace.INTERNAL in definition.workspaces:
        permissions.update(INTERNAL_VIEW_PERMISSIONS)
    if Capability.EDIT_INTERNAL in definition.capabilities:
        permissions.update(INTERNAL_EDIT_PERMISSIONS)
    if Workspace.RENTAL in definition.workspaces:
        permissions.update(RENTAL_VIEW_PERMISSIONS)
    if Capability.EDIT_RENTAL in definition.capabilities:
        permissions.update(RENTAL_EDIT_PERMISSIONS)

    if Capability.APPROVE in definition.capabilities:
        if Workspace.INTERNAL in definition.workspaces:
            permissions.update(INTERNAL_APPROVE_PERMISSIONS)
        if Workspace.RENTAL in definition.workspaces:
            permissions.update(RENTAL_APPROVE_PERMISSIONS)
    if Capability.PAY in definition.capabilities:
        if Workspace.INTERNAL in definition.workspaces:
            permissions.update(INTERNAL_PAY_PERMISSIONS)
        if Workspace.RENTAL in definition.workspaces:
            permissions.update(RENTAL_PAY_PERMISSIONS)

    if Capability.MANAGE_SETTINGS in definition.capabilities:
        permissions.update({AccessPermission.SETTINGS_VIEW, AccessPermission.SETTINGS_MANAGE})
    elif Workspace.MANAGEMENT in definition.workspaces:
        permissions.add(AccessPermission.SETTINGS_VIEW)
    if Capability.VIEW_AUDIT in definition.capabilities:
        permissions.add(AccessPermission.ACCESS_AUDIT_VIEW)
    if Capability.VIEW_ACCESS in definition.capabilities:
        permissions.update({AccessPermission.ACCESS_USERS_VIEW, AccessPermission.ACCESS_PROFILES_VIEW})
    if Capability.MANAGE_ACCESS in definition.capabilities:
        permissions.update({
            AccessPermission.ACCESS_USERS_VIEW,
            AccessPermission.ACCESS_USERS_MANAGE,
            AccessPermission.ACCESS_PROFILES_VIEW,
            AccessPermission.ACCESS_PROFILES_MANAGE,
        })

    if role == AccessRole.OWNER:
        return frozenset(AccessPermission)
    return frozenset(permissions)


def system_profile_key_for_role(role: str) -> str:
    return f"role-{role}"
