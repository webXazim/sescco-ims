from __future__ import annotations

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission


VENDOR_SOURCING_PERMISSIONS = frozenset({
    AccessPermission.SOURCING_VENDORS_VIEW,
    AccessPermission.SOURCING_VENDORS_MANAGE,
})
MANPOWER_SOURCING_PERMISSIONS = frozenset({
    AccessPermission.SOURCING_MANPOWER_VIEW,
    AccessPermission.SOURCING_MANPOWER_MANAGE,
})
MASTER_SOURCING_PERMISSIONS = frozenset({
    AccessPermission.SOURCING_MASTERS_VIEW,
    AccessPermission.SOURCING_MASTERS_MANAGE,
})
ALL_SOURCING_PERMISSIONS = frozenset({
    *VENDOR_SOURCING_PERMISSIONS,
    *MANPOWER_SOURCING_PERMISSIONS,
    *MASTER_SOURCING_PERMISSIONS,
    AccessPermission.SOURCING_EXPORT_EXECUTE,
})
VISIBLE_SOURCING_PERMISSIONS = frozenset({
    AccessPermission.SOURCING_VENDORS_VIEW,
    AccessPermission.SOURCING_MANPOWER_VIEW,
    AccessPermission.SOURCING_MASTERS_VIEW,
})


def membership_has_any_sourcing_access(membership) -> bool:
    # Module visibility is deliberately based on read authority only.
    # Access-profile validation normally prevents malformed action-only grants,
    # but this keeps the shell fail-closed even if data is edited out of band.
    return any(membership_has_permission(membership, permission) for permission in VISIBLE_SOURCING_PERMISSIONS)


def membership_can_view_vendor_sourcing(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_VENDORS_VIEW)


def membership_can_manage_vendor_sourcing(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_VENDORS_MANAGE)


def membership_can_view_manpower_sourcing(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_MANPOWER_VIEW)


def membership_can_manage_manpower_sourcing(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_MANPOWER_MANAGE)


def membership_can_view_sourcing_masters(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_MASTERS_VIEW)


def membership_can_manage_sourcing_masters(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_MASTERS_MANAGE)


def membership_can_export_sourcing(membership) -> bool:
    return membership_has_permission(membership, AccessPermission.SOURCING_EXPORT_EXECUTE)


def sourcing_access_context(membership) -> dict[str, object]:
    """Template-safe effective Sourcing authority for the current membership."""
    return {
        "vendors": {
            "view": membership_can_view_vendor_sourcing(membership),
            "manage": membership_can_manage_vendor_sourcing(membership),
        },
        "manpower": {
            "view": membership_can_view_manpower_sourcing(membership),
            "manage": membership_can_manage_manpower_sourcing(membership),
        },
        "masters": {
            "view": membership_can_view_sourcing_masters(membership),
            "manage": membership_can_manage_sourcing_masters(membership),
        },
        "export": membership_can_export_sourcing(membership),
    }
