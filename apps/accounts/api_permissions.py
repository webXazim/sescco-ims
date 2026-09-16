from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from django.http import HttpRequest, JsonResponse

from .access_catalog import AccessPermission
from .access_policy import membership_has_permission
from .permissions import membership_can_workspace
from .roles import Workspace

F = TypeVar("F", bound=Callable[..., JsonResponse])


def api_workspace_required(workspace: Workspace | str) -> Callable[[F], F]:
    """Require an authenticated active-company membership for JSON API views.

    Unlike Django's page-oriented authentication decorators, this returns JSON 401/403
    responses so the application client never receives an HTML login/permission page from
    an API request.
    """

    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            if not request.user.is_authenticated:
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your sign-in session is no longer active. Sign in again to continue."]}},
                    status=401,
                )

            membership = getattr(request, "company_membership", None)
            if membership is None:
                return JsonResponse(
                    {
                        "ok": False,
                        "errors": {"__all__": ["No active company access is assigned to this account."]},
                    },
                    status=403,
                )

            if not membership_can_workspace(membership, workspace):
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your access profile cannot access this workspace."]}},
                    status=403,
                )

            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def api_company_required(view_func: F) -> F:
    """Require an authenticated active company membership for workspace-neutral JSON APIs."""

    @wraps(view_func)
    def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        if not request.user.is_authenticated:
            return JsonResponse(
                {"ok": False, "errors": {"__all__": ["Your sign-in session is no longer active. Sign in again to continue."]}},
                status=401,
            )
        membership = getattr(request, "company_membership", None)
        if membership is None or not membership.is_active or not membership.company.is_active:
            return JsonResponse(
                {"ok": False, "errors": {"__all__": ["No active company access is assigned to this account."]}},
                status=403,
            )
        return view_func(request, *args, **kwargs)

    return wrapped  # type: ignore[return-value]


def api_access_permission_required(permission: AccessPermission | str) -> Callable[[F], F]:
    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            if not request.user.is_authenticated:
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your sign-in session is no longer active. Sign in again to continue."]}},
                    status=401,
                )
            membership = getattr(request, "company_membership", None)
            if membership is None:
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["No active company access is assigned to this account."]}},
                    status=403,
                )
            if not membership_has_permission(membership, permission):
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your access profile does not allow this action."]}},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator


def api_method_access_required(**method_permissions) -> Callable[[F], F]:
    """Require at least one exact permission for each mapped HTTP method.

    This is the page/action boundary for APIs that expose more than one operation
    under one URL. Values may be one permission or an iterable of permissions;
    matching is OR within a method. Methods omitted from the mapping fail closed.
    """
    normalized: dict[str, tuple[AccessPermission | str, ...]] = {}
    for method, permissions in method_permissions.items():
        if isinstance(permissions, (AccessPermission, str)):
            values = (permissions,)
        else:
            values = tuple(permissions)
        normalized[str(method).upper()] = values

    def decorator(view_func: F) -> F:
        @wraps(view_func)
        def wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            if not request.user.is_authenticated:
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your sign-in session is no longer active. Sign in again to continue."]}},
                    status=401,
                )
            membership = getattr(request, "company_membership", None)
            if membership is None:
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["No active company access is assigned to this account."]}},
                    status=403,
                )
            required = normalized.get(request.method.upper())
            if not required or not any(membership_has_permission(membership, permission) for permission in required):
                return JsonResponse(
                    {"ok": False, "errors": {"__all__": ["Your access profile does not allow this page or action."]}},
                    status=403,
                )
            return view_func(request, *args, **kwargs)

        return wrapped  # type: ignore[return-value]

    return decorator
