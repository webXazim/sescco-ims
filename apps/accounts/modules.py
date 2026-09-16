from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit

from .access_catalog import AccessPermission
from .access_policy import membership_has_permission
from .permissions import membership_can_workspace
from .roles import Workspace


class PlatformModule(StrEnum):
    INVENTORY = "inventory"
    PAYROLL = "payroll"
    ADMINISTRATION = "administration"
    SOURCING = "sourcing"


def membership_can_module(membership, module: PlatformModule | str) -> bool:
    try:
        value = PlatformModule(module)
    except ValueError:
        return False
    if value is PlatformModule.INVENTORY:
        return membership_can_workspace(membership, Workspace.INVENTORY)
    if value is PlatformModule.PAYROLL:
        return any(
            membership_can_workspace(membership, workspace)
            for workspace in (Workspace.INTERNAL, Workspace.RENTAL, Workspace.MANAGEMENT)
        )
    if value is PlatformModule.SOURCING:
        # Sourcing is an independently permissioned reference-only module. Inventory,
        # Payroll and other operational roles do not imply any Sourcing access.
        from apps.sourcing.access import membership_has_any_sourcing_access

        return membership_has_any_sourcing_access(membership)
    return membership_has_permission(membership, AccessPermission.ACCESS_USERS_VIEW)


def module_from_path(path: str) -> PlatformModule | None:
    normalized = urlsplit(str(path or "")).path
    if normalized.startswith("/app/administration/"):
        return PlatformModule.ADMINISTRATION
    if normalized.startswith("/app/payroll/"):
        return PlatformModule.PAYROLL
    if normalized.startswith("/app/sourcing/"):
        return PlatformModule.SOURCING
    if normalized.startswith("/app/"):
        return PlatformModule.INVENTORY
    return None


def module_home_name(module: PlatformModule | str) -> str:
    value = PlatformModule(module)
    if value is PlatformModule.INVENTORY:
        return "core:dashboard"
    if value is PlatformModule.PAYROLL:
        return "core:payroll"
    if value is PlatformModule.SOURCING:
        return "sourcing:home"
    return "accounts:administration"
