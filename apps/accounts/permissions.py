from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from .models import CompanyMembership
from .roles import Capability, Workspace, role_definition

F = TypeVar("F", bound=Callable[..., HttpResponse])


def _membership_is_usable(membership: CompanyMembership | None) -> bool:
    return bool(
        membership is not None
        and membership.is_active
        and membership.user.is_active
        and membership.company.is_active
    )


def membership_can_workspace(membership: CompanyMembership | None, workspace: Workspace | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    return role_definition(membership.role).has_workspace(workspace)


def membership_can_edit(membership: CompanyMembership | None, workspace: Workspace | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    return role_definition(membership.role).can_edit(workspace)


def membership_has_capability(membership: CompanyMembership | None, capability: Capability | str) -> bool:
    if not _membership_is_usable(membership):
        return False
    return role_definition(membership.role).has(capability)




def user_membership_for_company(user, company) -> CompanyMembership | None:
    if user is None or company is None or not getattr(user, "is_authenticated", False):
        return None
    return (
        CompanyMembership.objects.select_related("company", "user")
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
                raise PermissionDenied("Your company role does not allow access to this workspace.")
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def capability_required(capability: Capability | str) -> Callable[[F], F]:
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not membership_has_capability(getattr(request, "company_membership", None), capability):
                raise PermissionDenied("Your company role does not allow this action.")
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
