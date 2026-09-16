from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from .access_catalog import (
    AccessPermission,
    INTERNAL_APPROVE_PERMISSIONS,
    INTERNAL_EDIT_PERMISSIONS,
    INTERNAL_PAY_PERMISSIONS,
    INTERNAL_REVIEW_PERMISSIONS,
    INTERNAL_VIEW_PERMISSIONS,
    INVENTORY_EDIT_PERMISSIONS,
    INVENTORY_MANAGE_PERMISSIONS,
    INVENTORY_VIEW_PERMISSIONS,
    RENTAL_APPROVE_PERMISSIONS,
    RENTAL_EDIT_PERMISSIONS,
    RENTAL_PAY_PERMISSIONS,
    RENTAL_VIEW_PERMISSIONS,
)
from .access_policy import effective_access_for_membership, membership_has_permission
from .models import CompanyMembership
from .roles import Capability, Workspace

F = TypeVar("F", bound=Callable[..., HttpResponse])


_MANAGEMENT_VIEW_PERMISSIONS = frozenset({
    AccessPermission.ACCESS_USERS_VIEW,
    AccessPermission.ACCESS_USERS_MANAGE,
    AccessPermission.ACCESS_PROFILES_VIEW,
    AccessPermission.ACCESS_PROFILES_MANAGE,
    AccessPermission.ACCESS_AUDIT_VIEW,
    AccessPermission.SETTINGS_VIEW,
    AccessPermission.SETTINGS_MANAGE,
})


def _membership_is_usable(membership: CompanyMembership | None) -> bool:
    return bool(
        membership is not None
        and membership.is_active
        and membership.user.is_active
        and membership.company.is_active
    )


def _permission_values(membership: CompanyMembership | None) -> frozenset[str]:
    access = effective_access_for_membership(membership)
    return access.permissions if access is not None else frozenset()


def _has_any(membership: CompanyMembership | None, permissions) -> bool:
    values = _permission_values(membership)
    return any(permission.value in values for permission in permissions)


def membership_can_workspace(membership: CompanyMembership | None, workspace: Workspace | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    try:
        value = Workspace(workspace)
    except ValueError:
        return False
    if value is Workspace.INVENTORY:
        return _has_any(membership, INVENTORY_VIEW_PERMISSIONS | INVENTORY_EDIT_PERMISSIONS | INVENTORY_MANAGE_PERMISSIONS | {AccessPermission.INVENTORY_IMPORT_EXECUTE})
    if value is Workspace.INTERNAL:
        return _has_any(membership, INTERNAL_VIEW_PERMISSIONS | INTERNAL_EDIT_PERMISSIONS | INTERNAL_REVIEW_PERMISSIONS | INTERNAL_APPROVE_PERMISSIONS | INTERNAL_PAY_PERMISSIONS)
    if value is Workspace.RENTAL:
        return _has_any(membership, RENTAL_VIEW_PERMISSIONS | RENTAL_EDIT_PERMISSIONS | RENTAL_APPROVE_PERMISSIONS | RENTAL_PAY_PERMISSIONS)
    return _has_any(membership, _MANAGEMENT_VIEW_PERMISSIONS)


def membership_can_edit(membership: CompanyMembership | None, workspace: Workspace | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    try:
        value = Workspace(workspace)
    except ValueError:
        return False
    if value is Workspace.INVENTORY:
        return _has_any(membership, INVENTORY_EDIT_PERMISSIONS | INVENTORY_MANAGE_PERMISSIONS | {AccessPermission.INVENTORY_IMPORT_EXECUTE})
    if value is Workspace.INTERNAL:
        return _has_any(membership, INTERNAL_EDIT_PERMISSIONS)
    if value is Workspace.RENTAL:
        return _has_any(membership, RENTAL_EDIT_PERMISSIONS)
    return False


def membership_has_capability(membership: CompanyMembership | None, capability: Capability | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    try:
        value = Capability(capability)
    except ValueError:
        return False
    if value is Capability.EDIT_INVENTORY:
        return _has_any(membership, INVENTORY_EDIT_PERMISSIONS)
    if value is Capability.MANAGE_INVENTORY:
        return _has_any(membership, INVENTORY_MANAGE_PERMISSIONS)
    if value is Capability.IMPORT_INVENTORY:
        return membership_has_permission(membership, AccessPermission.INVENTORY_IMPORT_EXECUTE)
    if value is Capability.EDIT_INTERNAL:
        return _has_any(membership, INTERNAL_EDIT_PERMISSIONS)
    if value is Capability.EDIT_RENTAL:
        return _has_any(membership, RENTAL_EDIT_PERMISSIONS)
    if value is Capability.APPROVE:
        return _has_any(membership, INTERNAL_APPROVE_PERMISSIONS | RENTAL_APPROVE_PERMISSIONS)
    if value is Capability.PAY:
        return _has_any(membership, INTERNAL_PAY_PERMISSIONS | RENTAL_PAY_PERMISSIONS)
    if value is Capability.MANAGE_SETTINGS:
        return membership_has_permission(membership, AccessPermission.SETTINGS_MANAGE)
    if value is Capability.VIEW_AUDIT:
        return membership_has_permission(membership, AccessPermission.ACCESS_AUDIT_VIEW)
    if value is Capability.VIEW_ACCESS:
        return _has_any(membership, {AccessPermission.ACCESS_USERS_VIEW, AccessPermission.ACCESS_PROFILES_VIEW})
    if value is Capability.MANAGE_ACCESS:
        return _has_any(membership, {AccessPermission.ACCESS_USERS_MANAGE, AccessPermission.ACCESS_PROFILES_MANAGE})
    return False


def user_membership_for_company(user, company) -> CompanyMembership | None:
    if user is None or company is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        CompanyMembership.objects.select_related("company", "user", "access_profile")
        .prefetch_related("access_profile__permission_grants")
        .filter(user=user, company=company, is_active=True, company__is_active=True)
        .first()
    )


def user_has_capability_for_company(user, company, capability: Capability | str) -> bool:
    return membership_has_capability(user_membership_for_company(user, company), capability)


def user_can_workspace_for_company(user, company, workspace: Workspace | str) -> bool:
    return membership_can_workspace(user_membership_for_company(user, company), workspace)


def company_access_required(view_func: F) -> F:
    @wraps(view_func)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        membership = getattr(request, "company_membership", None)
        if membership is None:
            raise PermissionDenied("No active company access is assigned to this account.")
        return view_func(request, *args, **kwargs)

    return wrapped  # type: ignore[return-value]


def workspace_required(workspace: Workspace | str) -> Callable[[F], F]:
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not membership_can_workspace(getattr(request, "company_membership", None), workspace):
                raise PermissionDenied("Your access profile does not allow access to this workspace.")
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def capability_required(capability: Capability | str) -> Callable[[F], F]:
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not membership_has_capability(getattr(request, "company_membership", None), capability):
                raise PermissionDenied("Your access profile does not allow this action.")
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def access_permission_required(permission: AccessPermission | str) -> Callable[[F], F]:
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not membership_has_permission(getattr(request, "company_membership", None), permission):
                raise PermissionDenied("Your access profile does not allow this action.")
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
