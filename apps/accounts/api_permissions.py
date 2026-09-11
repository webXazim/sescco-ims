from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from django.http import HttpRequest, JsonResponse

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
                    {"ok": False, "errors": {"__all__": ["Your role cannot access this workspace."]}},
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
