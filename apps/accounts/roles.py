from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from django.db import models


class AccessRole(models.TextChoices):
    OWNER = "owner", "Company Owner"
    OPERATIONS_ADMIN = "operations-admin", "Operations Administrator"
    INVENTORY_MANAGER = "inventory-manager", "Inventory Manager"
    STOREKEEPER = "storekeeper", "Storekeeper"
    FINANCE_MANAGER = "finance", "Finance Manager"
    INTERNAL_PAYROLL_OFFICER = "internal-officer", "Internal Payroll Officer"
    RENTAL_MANPOWER_OFFICER = "rental-officer", "Rental Manpower Officer"
    FINANCE_REVIEWER = "reviewer", "Finance Reviewer"
    READ_ONLY_AUDITOR = "auditor", "Read-only Auditor"


class Workspace(StrEnum):
    MANAGEMENT = "management"
    INVENTORY = "inventory"
    INTERNAL = "internal"
    RENTAL = "rental"


class Capability(StrEnum):
    EDIT_INVENTORY = "edit_inventory"
    MANAGE_INVENTORY = "manage_inventory"
    IMPORT_INVENTORY = "import_inventory"
    EDIT_INTERNAL = "edit_internal"
    EDIT_RENTAL = "edit_rental"
    APPROVE = "approve"
    PAY = "pay"
    MANAGE_SETTINGS = "manage_settings"
    VIEW_AUDIT = "view_audit"
    VIEW_ACCESS = "view_access"
    MANAGE_ACCESS = "manage_access"


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    label: str
    workspaces: tuple[Workspace, ...]
    edit_workspaces: tuple[Workspace, ...]
    capabilities: frozenset[Capability]
    description: str

    def has_workspace(self, workspace: Workspace | str) -> bool:
        try:
            value = Workspace(workspace)
        except ValueError:
            return False
        return value in self.workspaces

    def can_edit(self, workspace: Workspace | str) -> bool:
        try:
            value = Workspace(workspace)
        except ValueError:
            return False
        return value in self.edit_workspaces

    def has(self, capability: Capability | str) -> bool:
        try:
            value = Capability(capability)
        except ValueError:
            return False
        return value in self.capabilities

    def as_frontend_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "workspaces": [item.value for item in self.workspaces],
            "edit": [item.value for item in self.edit_workspaces],
            "capabilities": sorted(item.value for item in self.capabilities),
            "approve": Capability.APPROVE in self.capabilities,
            "pay": Capability.PAY in self.capabilities,
            "settings": Capability.MANAGE_SETTINGS in self.capabilities,
            "audit": Capability.VIEW_AUDIT in self.capabilities,
            "view_access": Capability.VIEW_ACCESS in self.capabilities,
            "manage_access": Capability.MANAGE_ACCESS in self.capabilities,
            "description": self.description,
        }


ROLE_DEFINITIONS: dict[str, RoleDefinition] = {
    AccessRole.OWNER: RoleDefinition(
        label=AccessRole.OWNER.label,
        workspaces=(Workspace.MANAGEMENT, Workspace.INVENTORY, Workspace.INTERNAL, Workspace.RENTAL),
        edit_workspaces=(Workspace.INVENTORY, Workspace.INTERNAL, Workspace.RENTAL),
        capabilities=frozenset(Capability),
        description=(
            "Full company authority across Inventory, Internal Payroll, Rental Manpower, "
            "approvals, payments, settings, audit and access control."
        ),
    ),
    AccessRole.OPERATIONS_ADMIN: RoleDefinition(
        label=AccessRole.OPERATIONS_ADMIN.label,
        workspaces=(Workspace.MANAGEMENT, Workspace.INVENTORY),
        edit_workspaces=(Workspace.INVENTORY,),
        capabilities=frozenset({
            Capability.EDIT_INVENTORY,
            Capability.MANAGE_INVENTORY,
            Capability.IMPORT_INVENTORY,
            Capability.MANAGE_SETTINGS,
            Capability.VIEW_AUDIT,
            Capability.VIEW_ACCESS,
        }),
        description=(
            "Inventory and operational administration without automatic payroll, salary, "
            "approval, payment or access-management authority."
        ),
    ),
    AccessRole.INVENTORY_MANAGER: RoleDefinition(
        label=AccessRole.INVENTORY_MANAGER.label,
        workspaces=(Workspace.INVENTORY,),
        edit_workspaces=(Workspace.INVENTORY,),
        capabilities=frozenset({
            Capability.EDIT_INVENTORY,
            Capability.MANAGE_INVENTORY,
            Capability.IMPORT_INVENTORY,
        }),
        description="Full Inventory operations, corrective actions, projects and import authority.",
    ),
    AccessRole.STOREKEEPER: RoleDefinition(
        label=AccessRole.STOREKEEPER.label,
        workspaces=(Workspace.INVENTORY,),
        edit_workspaces=(Workspace.INVENTORY,),
        capabilities=frozenset({Capability.EDIT_INVENTORY}),
        description=(
            "Day-to-day stock entry, usage and transfer access without destructive corrective "
            "actions or administrative imports."
        ),
    ),
    AccessRole.FINANCE_MANAGER: RoleDefinition(
        label=AccessRole.FINANCE_MANAGER.label,
        workspaces=(Workspace.MANAGEMENT, Workspace.INTERNAL, Workspace.RENTAL),
        edit_workspaces=(Workspace.INTERNAL, Workspace.RENTAL),
        capabilities=frozenset({
            Capability.EDIT_INTERNAL,
            Capability.EDIT_RENTAL,
            Capability.APPROVE,
            Capability.PAY,
            Capability.VIEW_AUDIT,
            Capability.VIEW_ACCESS,
        }),
        description=(
            "Cross-payroll finance control, operational edits, approvals, payments, audit and "
            "access-policy visibility without Inventory mutation authority."
        ),
    ),
    AccessRole.INTERNAL_PAYROLL_OFFICER: RoleDefinition(
        label=AccessRole.INTERNAL_PAYROLL_OFFICER.label,
        workspaces=(Workspace.INTERNAL,),
        edit_workspaces=(Workspace.INTERNAL,),
        capabilities=frozenset({Capability.EDIT_INTERNAL}),
        description="Internal employees, attendance, payroll preparation and bank/WPS setup only.",
    ),
    AccessRole.RENTAL_MANPOWER_OFFICER: RoleDefinition(
        label=AccessRole.RENTAL_MANPOWER_OFFICER.label,
        workspaces=(Workspace.RENTAL,),
        edit_workspaces=(Workspace.RENTAL,),
        capabilities=frozenset({Capability.EDIT_RENTAL}),
        description=(
            "Rental workers, manpower suppliers, assignments, timesheets and settlement "
            "preparation only."
        ),
    ),
    AccessRole.FINANCE_REVIEWER: RoleDefinition(
        label=AccessRole.FINANCE_REVIEWER.label,
        workspaces=(Workspace.MANAGEMENT, Workspace.INTERNAL, Workspace.RENTAL),
        edit_workspaces=(),
        capabilities=frozenset({Capability.APPROVE, Capability.VIEW_AUDIT}),
        description="Read across Payroll with controlled review/approval authority and no payments.",
    ),
    AccessRole.READ_ONLY_AUDITOR: RoleDefinition(
        label=AccessRole.READ_ONLY_AUDITOR.label,
        workspaces=(Workspace.MANAGEMENT,),
        edit_workspaces=(),
        capabilities=frozenset({Capability.VIEW_AUDIT}),
        description="Read-only management and audit visibility with no operational changes.",
    ),
}


def role_definition(role: str) -> RoleDefinition:
    try:
        return ROLE_DEFINITIONS[role]
    except KeyError as exc:
        raise ValueError(f"Unknown access role: {role}") from exc


def role_matrix_for_frontend() -> dict[str, dict[str, object]]:
    return {key: value.as_frontend_dict() for key, value in ROLE_DEFINITIONS.items()}
