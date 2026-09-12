from __future__ import annotations

import json
import mimetypes
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.utils import timezone

from apps.accounts.api_permissions import api_company_required
from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.core.selectors.settings import company_settings
from apps.core.services.settings import update_company_brand_asset, update_company_settings


def _errors(exc: ValidationError) -> dict[str, list[str]]:
    if hasattr(exc, "message_dict"):
        return {key: [str(item) for item in value] for key, value in exc.message_dict.items()}
    return {"__all__": [str(item) for item in getattr(exc, "messages", [str(exc)])]}



def _text(body: dict, key: str, default: str) -> str:
    value = body[key] if key in body else default
    if not isinstance(value, str):
        raise ValidationError({key: "A text value is required."})
    return value.strip()


_BRAND_ASSET_FIELDS = {
    "logo": "document_logo",
    "letterhead": "document_letterhead",
    "watermark": "document_watermark",
}
_BRAND_MAX_BYTES = {"logo": 2 * 1024 * 1024, "letterhead": 8 * 1024 * 1024, "watermark": 4 * 1024 * 1024}


def _branding_payload(request: HttpRequest, settings) -> dict[str, object]:
    payload: dict[str, object] = {"mode": settings.document_branding_mode}
    for kind, field_name in _BRAND_ASSET_FIELDS.items():
        field = getattr(settings, field_name)
        payload[kind] = {
            "configured": bool(field and field.name),
            "url": reverse("platform_api:company-branding-asset", kwargs={"kind": kind}) if field and field.name else "",
        }
    return payload


def _validated_image(uploaded, kind: str):
    if uploaded is None:
        raise ValidationError({"asset": "Choose an image to upload."})
    if uploaded.size <= 0 or uploaded.size > _BRAND_MAX_BYTES[kind]:
        raise ValidationError({"asset": f"{kind.title()} image exceeds the allowed size."})
    head = uploaded.read(16)
    uploaded.seek(0)
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = "image/png"
        ext = ".png"
    elif head.startswith(b"\xff\xd8\xff"):
        detected = "image/jpeg"
        ext = ".jpg"
    elif len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        detected = "image/webp"
        ext = ".webp"
    else:
        raise ValidationError({"asset": "Upload a PNG, JPEG or WebP image."})
    if not uploaded.name.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        uploaded.name = f"{kind}{ext}"
    uploaded.content_type = detected
    return uploaded, detected


def _serialize(request: HttpRequest, settings=None) -> dict[str, object]:
    settings = settings or company_settings(request.company)
    company_today = timezone.now().astimezone(ZoneInfo(settings.timezone)).date().isoformat()
    return {
        "companyName": request.company.name,
        "legalName": request.company.legal_name,
        "timezone": settings.timezone,
        "currency": settings.currency_code,
        "country": settings.country_code,
        "commercialRegistration": settings.commercial_registration,
        "vatNumber": settings.vat_number,
        "documentAddress": settings.document_address,
        "documentEmail": settings.document_email,
        "documentPhone": settings.document_phone,
        "website": settings.website,
        "documentBrandingMode": settings.document_branding_mode,
        "branding": _branding_payload(request, settings),
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
            commercial_registration=_text(body, "commercialRegistration", current.commercial_registration),
            vat_number=_text(body, "vatNumber", current.vat_number),
            document_address=_text(body, "documentAddress", current.document_address),
            document_email=_text(body, "documentEmail", current.document_email),
            document_phone=_text(body, "documentPhone", current.document_phone),
            website=_text(body, "website", current.website),
            document_branding_mode=_text(body, "documentBrandingMode", current.document_branding_mode),
            request=request,
        )
        return JsonResponse({"ok": True, "settings": _serialize(request, updated_settings)})
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Invalid JSON payload."]}}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": _errors(exc)}, status=400)


@require_http_methods(["GET", "POST", "DELETE"])
@api_company_required
def company_branding_asset_api(request: HttpRequest, kind: str):
    kind = str(kind).strip().lower()
    field_name = _BRAND_ASSET_FIELDS.get(kind)
    if field_name is None:
        return JsonResponse({"ok": False, "errors": {"kind": ["Unsupported branding asset."]}}, status=404)
    try:
        current = company_settings(request.company)
        if request.method == "GET":
            field = getattr(current, field_name)
            if not field or not field.name:
                return JsonResponse({"ok": False, "errors": {"asset": ["Branding asset is not configured."]}}, status=404)
            response = FileResponse(field.open("rb"), content_type=mimetypes.guess_type(field.name)[0] or "application/octet-stream")
            response["Cache-Control"] = "private, no-store"
            response["X-Content-Type-Options"] = "nosniff"
            return response
        if request.method == "DELETE":
            updated = update_company_brand_asset(
                actor_membership=request.company_membership, kind=kind, clear=True, request=request
            )
        else:
            uploaded, _detected = _validated_image(request.FILES.get("asset"), kind)
            updated = update_company_brand_asset(
                actor_membership=request.company_membership, kind=kind, uploaded_file=uploaded, request=request
            )
        return JsonResponse({"ok": True, "branding": _branding_payload(request, updated)})
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": _errors(exc)}, status=400)
