from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlsplit

from .permissions import membership_can_workspace
from .roles import Workspace


class PlatformModule(StrEnum):
    INVENTORY = "inventory"
    PAYROLL = "payroll"


def membership_can_module(membership, module: PlatformModule | str) -> bool:
    try:
        value = PlatformModule(module)
    except ValueError:
        return False
    if value is PlatformModule.INVENTORY:
        return membership_can_workspace(membership, Workspace.INVENTORY)
    return any(
        membership_can_workspace(membership, workspace)
        for workspace in (Workspace.INTERNAL, Workspace.RENTAL, Workspace.MANAGEMENT)
    )


def module_from_path(path: str) -> PlatformModule | None:
    normalized = urlsplit(str(path or "")).path
    if normalized.startswith("/app/payroll/"):
        return PlatformModule.PAYROLL
    if normalized.startswith("/app/"):
        return PlatformModule.INVENTORY
    return None


def module_home_name(module: PlatformModule | str) -> str:
    value = PlatformModule(module)
    return "core:dashboard" if value is PlatformModule.INVENTORY else "core:payroll"
