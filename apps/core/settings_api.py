from __future__ import annotations

import json
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from apps.accounts.api_permissions import api_company_required
from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.core.selectors.settings import company_settings
from apps.core.services.settings import update_company_settings


def _errors(exc: ValidationError) -> dict[str, list[str]]:
    if hasattr(exc, "message_dict"):
        return {key: [str(item) for item in value] for key, value in exc.message_dict.items()}
    return {"__all__": [str(item) for item in getattr(exc, "messages", [str(exc)])]}



def _text(body: dict, key: str, default: str) -> str:
    value = body[key] if key in body else default
    if not isinstance(value, str):
        raise ValidationError({key: "A text value is required."})
    return value.strip()


def _serialize(request: HttpRequest, settings=None) -> dict[str, object]:
    settings = settings or company_settings(request.company)
    company_today = timezone.now().astimezone(ZoneInfo(settings.timezone)).date().isoformat()
    return {
        "companyName": request.company.name,
        "legalName": request.company.legal_name,
        "timezone": settings.timezone,
        "currency": settings.currency_code,
        "country": settings.country_code,
        "today": company_today,
        "canManage": membership_has_capability(request.company_membership, Capability.MANAGE_SETTINGS),
    }


@require_http_methods(["GET", "PATCH"])
@api_company_required
def company_settings_api(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"ok": True, "settings": _serialize(request)})

    try:
        body = json.loads(request.body or b"{}")
        if not isinstance(body, dict):
            raise ValidationError({"__all__": "A JSON object is required."})
        current = company_settings(request.company)
        updated_settings = update_company_settings(
            actor_membership=request.company_membership,
            company_name=_text(body, "companyName", request.company.name),
            legal_name=_text(body, "legalName", request.company.legal_name),
            timezone=_text(body, "timezone", current.timezone),
            currency_code=_text(body, "currency", current.currency_code),
            country_code=_text(body, "country", current.country_code),
            request=request,
        )
        return JsonResponse({"ok": True, "settings": _serialize(request, updated_settings)})
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Invalid JSON payload."]}}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": _errors(exc)}, status=400)
