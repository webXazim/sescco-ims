from __future__ import annotations

from .access_policy import effective_access_for_membership
from .permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from .roles import Capability, Workspace, role_matrix_for_frontend


def access_context_for_request(request) -> dict[str, object]:
    membership = getattr(request, "company_membership", None)
    company = getattr(request, "company", None)
    if membership is None or company is None:
        return {}

    effective_access = getattr(request, "effective_access", None) or effective_access_for_membership(membership)
    workspaces = [workspace.value for workspace in Workspace if membership_can_workspace(membership, workspace)]
    edit_workspaces = [workspace.value for workspace in Workspace if membership_can_edit(membership, workspace)]
    capabilities = [capability.value for capability in Capability if membership_has_capability(membership, capability)]
    profile_name = effective_access.profile_name if effective_access else "No access profile"
    return {
        "company_id": str(company.id),
        "company_name": company.name,
        "membership_id": str(membership.id),
        # Compatibility classification only. Browser/backend authorization must use
        # workspaces/capabilities/effective_access below, all derived from AccessProfile.
        "role": membership.role,
        "role_label": profile_name,
        "role_matrix": role_matrix_for_frontend(),
        "workspaces": workspaces,
        "edit_workspaces": edit_workspaces,
        "capabilities": sorted(capabilities),
        "effective_access": effective_access.as_frontend_dict() if effective_access else {},
        "must_change_password": bool(membership.user.must_change_password),
    }


def platform_context_for_request(request) -> dict[str, object]:
    from django.urls import reverse

    from .modules import PlatformModule, membership_can_module, module_from_path

    membership = getattr(request, "company_membership", None)
    company = getattr(request, "company", None)
    current_module = module_from_path(getattr(request, "path", ""))
    modules = []
    if membership_can_module(membership, PlatformModule.INVENTORY):
        modules.append({
            "key": PlatformModule.INVENTORY.value,
            "label": "Inventory Management",
            "description": "Stock, projects, suppliers and movements",
            "url": reverse("core:dashboard"),
            "available": True,
            "active": current_module is PlatformModule.INVENTORY,
            "code": "IM",
        })
    if membership_can_module(membership, PlatformModule.PAYROLL):
        modules.append({
            "key": PlatformModule.PAYROLL.value,
            "label": "Payroll Management",
            "description": "Internal payroll and rental manpower",
            "url": reverse("core:payroll"),
            "available": True,
            "active": current_module is PlatformModule.PAYROLL,
            "code": "PM",
        })
    if membership_can_module(membership, PlatformModule.SOURCING):
        modules.append({
            "key": PlatformModule.SOURCING.value,
            "label": "Sourcing Directory",
            "description": "Reference-only vendor and manpower sourcing",
            "url": reverse("sourcing:home"),
            "available": True,
            "active": current_module is PlatformModule.SOURCING,
            "code": "SD",
        })
    if membership_can_module(membership, PlatformModule.ADMINISTRATION):
        modules.append({
            "key": PlatformModule.ADMINISTRATION.value,
            "label": "Administration",
            "description": "Users, access profiles and permissions",
            "url": reverse("accounts:administration"),
            "available": True,
            "active": current_module is PlatformModule.ADMINISTRATION,
            "code": "AD",
        })
    return {
        "current_module": current_module.value if current_module else None,
        "modules": modules,
        "company_id": str(company.id) if company is not None else None,
        "company_name": company.name if company is not None else None,
    }
