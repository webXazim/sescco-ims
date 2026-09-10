from __future__ import annotations

import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone

from .request_context import company_id_var, request_id_var

_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdMiddleware:
    """Attach a safe correlation ID to each request and response."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get("X-Request-ID", "").strip()
        request_id = incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        request.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)


class CompanyTimezoneMiddleware:
    """Activate the authenticated company timezone when company context is available.

    ``CompanyContextMiddleware`` resolves ``request.company`` first. Requests without an active
    company membership safely fall back to Django's configured TIME_ZONE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        company = getattr(request, "company", None)
        company_token = company_id_var.set(str(getattr(company, "pk", "-") or "-"))
        timezone_name = None
        if company is not None:
            try:
                timezone_name = company.settings.timezone
            except (AttributeError, ObjectDoesNotExist):
                timezone_name = None

        if timezone_name:
            try:
                timezone.activate(ZoneInfo(timezone_name))
            except ZoneInfoNotFoundError:
                timezone.deactivate()
        else:
            timezone.deactivate()

        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
            company_id_var.reset(company_token)
