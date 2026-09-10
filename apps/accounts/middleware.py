from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from .selectors import ACTIVE_COMPANY_SESSION_KEY, resolve_membership


class CompanyContextMiddleware:
    """Resolve the authenticated user's active company membership for every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request.company = None
        request.company_membership = None

        if request.user.is_authenticated:
            requested_company_id = request.session.get(ACTIVE_COMPANY_SESSION_KEY)
            membership = resolve_membership(request.user, requested_company_id)
            if membership is not None:
                request.company_membership = membership
                request.company = membership.company
                canonical_id = str(membership.company_id)
                if requested_company_id != canonical_id:
                    request.session[ACTIVE_COMPANY_SESSION_KEY] = canonical_id
            elif requested_company_id:
                request.session.pop(ACTIVE_COMPANY_SESSION_KEY, None)

        return self.get_response(request)
