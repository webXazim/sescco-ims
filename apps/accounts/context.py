from __future__ import annotations

from .roles import role_definition, role_matrix_for_frontend


def access_context_for_request(request) -> dict[str, object]:
    membership = getattr(request, "company_membership", None)
    company = getattr(request, "company", None)
    if membership is None or company is None:
        return {}

    definition = role_definition(membership.role)
    return {
        "company_id": str(company.id),
        "company_name": company.name,
        "membership_id": str(membership.id),
        "role": membership.role,
        "role_label": definition.label,
        "role_matrix": role_matrix_for_frontend(),
        "workspaces": [item.value for item in definition.workspaces],
        "capabilities": sorted(item.value for item in definition.capabilities),
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
    return {
        "current_module": current_module.value if current_module else None,
        "modules": modules,
        "company_id": str(company.id) if company is not None else None,
        "company_name": company.name if company is not None else None,
    }
