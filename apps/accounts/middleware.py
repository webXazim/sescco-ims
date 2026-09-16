from __future__ import annotations

from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .access_policy import effective_access_for_membership
from .security import SESSION_SECURITY_VERSION_KEY, stamp_security_session
from .selectors import ACTIVE_COMPANY_SESSION_KEY, resolve_membership


class SecuritySessionMiddleware:
    """Invalidate stale authenticated sessions after authorization/security changes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated:
            current_version = int(request.user.security_version)
            session_version = request.session.get(SESSION_SECURITY_VERSION_KEY)
            if session_version is None:
                # Safe upgrade path for sessions created before 1.0.97. They immediately
                # receive the current server version; all later security changes invalidate them.
                stamp_security_session(request)
            else:
                try:
                    stale = int(session_version) != current_version
                except (TypeError, ValueError):
                    stale = True
                if stale:
                    logout(request)
                    if request.path.startswith("/api/"):
                        return JsonResponse(
                            {
                                "ok": False,
                                "code": "session_revoked",
                                "errors": {"__all__": ["Your access changed. Sign in again."]},
                            },
                            status=401,
                        )
                    return redirect(f"{reverse('accounts:login')}?reason=access-updated")
        return self.get_response(request)


class CompanyContextMiddleware:
    """Resolve the authenticated user's active company membership for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.company = None
        request.company_membership = None
        request.effective_access = None

        if request.user.is_authenticated:
            requested_company_id = request.session.get(ACTIVE_COMPANY_SESSION_KEY)
            membership = resolve_membership(request.user, requested_company_id)
            if membership is not None:
                request.company_membership = membership
                request.company = membership.company
                request.effective_access = effective_access_for_membership(membership)
                canonical_id = str(membership.company_id)
                if requested_company_id != canonical_id:
                    request.session[ACTIVE_COMPANY_SESSION_KEY] = canonical_id
            elif requested_company_id:
                request.session.pop(ACTIVE_COMPANY_SESSION_KEY, None)

        return self.get_response(request)


class MandatoryPasswordChangeMiddleware:
    """Block operational access until a temporary password has been replaced."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.user.is_authenticated and request.user.must_change_password:
            change_path = reverse("accounts:change-password")
            logout_path = reverse("accounts:logout")
            if request.path not in {change_path, logout_path}:
                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {
                            "ok": False,
                            "code": "password_change_required",
                            "errors": {"__all__": ["Change the temporary password before continuing."]},
                        },
                        status=428,
                    )
                return redirect(change_path)
        return self.get_response(request)
