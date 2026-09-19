from __future__ import annotations

import json
import logging
from datetime import date

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.http import HttpRequest, JsonResponse


logger = logging.getLogger(__name__)


def json_body(request: HttpRequest) -> dict[str, object]:
    if request.content_type != "application/json":
        raise ValidationError("Content-Type must be application/json.")
    try:
        value = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Request body is not valid JSON.") from exc
    if not isinstance(value, dict):
        raise ValidationError("JSON request body must be an object.")
    return value


def parse_date(value: object, field: str) -> date:
    if not isinstance(value, str):
        raise ValidationError({field: "Enter a valid date in YYYY-MM-DD format."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: "Enter a valid date in YYYY-MM-DD format."}) from exc


def parse_optional_date(value: object, field: str) -> date | None:
    if value in (None, ""):
        return None
    return parse_date(value, field)


def validation_errors(exc: ValidationError) -> dict[str, list[str]]:
    if hasattr(exc, "message_dict"):
        return {key: [str(item) for item in values] for key, values in exc.message_dict.items()}
    return {"__all__": [str(item) for item in exc.messages]}


def handle_api_error(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValidationError):
        return JsonResponse({"ok": False, "errors": validation_errors(exc)}, status=400)
    if isinstance(exc, ObjectDoesNotExist):
        return JsonResponse({"ok": False, "errors": {"__all__": ["Record not found."]}}, status=404)
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    if isinstance(exc, IntegrityError):
        return JsonResponse({"ok": False, "errors": {"__all__": ["The request conflicts with an existing record."]}}, status=409)

    # Rental Payroll is an SPA surface: returning Django's HTML 500 page makes the
    # browser report the misleading "server returned an invalid response" message and
    # hides the real HTTP status.  Preserve the traceback in server logs while keeping
    # every /api/rental/* failure on the JSON contract expected by the frontend.
    logger.error(
        "Unhandled Rental Manpower API error",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JsonResponse(
        {
            "ok": False,
            "errors": {
                "__all__": [
                    "The server could not complete this Rental Manpower request. Please retry; if it continues, check the server log for this request."
                ]
            },
        },
        status=500,
    )
