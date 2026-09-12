from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.utils import timezone

from apps.accounts.api_permissions import api_company_required
from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.core.selectors.settings import company_settings
from apps.core.services.settings import update_company_settings
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event


def _errors(exc: ValidationError) -> dict[str, list[str]]:
    if hasattr(exc, "message_dict"):
        return {key: [str(item) for item in value] for key, value in exc.message_dict.items()}
    return {"__all__": [str(item) for item in getattr(exc, "messages", [str(exc)])]}



def _text(body: dict, key: str, default: str) -> str:
    value = body[key] if key in body else default
    if not isinstance(value, str):
        raise ValidationError({key: "A text value is required."})
    return value.strip()


ASSET_FIELDS = {
    "logo": "document_logo",
    "letterhead": "document_letterhead",
    "watermark": "document_watermark",
}


def _asset_payload(request: HttpRequest, settings, kind: str) -> dict[str, object]:
    field_name = ASSET_FIELDS[kind]
    file_field = getattr(settings, field_name)
    configured = bool(file_field and file_field.name)
    return {
        "configured": configured,
        "filename": Path(file_field.name).name if configured else "",
        "url": reverse("platform_api:company-document-asset-file", kwargs={"asset_kind": kind}) if configured else "",
    }


def _validate_image_signature(uploaded) -> None:
    name = (uploaded.name or "").lower()
    head = uploaded.read(16)
    uploaded.seek(0)
    valid = (
        (name.endswith(".png") and head.startswith(b"\x89PNG\r\n\x1a\n"))
        or (name.endswith((".jpg", ".jpeg")) and head.startswith(b"\xff\xd8\xff"))
        or (name.endswith(".webp") and head[:4] == b"RIFF" and head[8:12] == b"WEBP")
    )
    if not valid:
        raise ValidationError({"file": "Upload a valid PNG, JPEG, or WebP image."})


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
        "documentAssets": {kind: _asset_payload(request, settings, kind) for kind in ASSET_FIELDS},
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
            request=request,
        )
        return JsonResponse({"ok": True, "settings": _serialize(request, updated_settings)})
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "errors": {"__all__": ["Invalid JSON payload."]}}, status=400)
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": _errors(exc)}, status=400)


@require_http_methods(["POST", "DELETE"])
@api_company_required
def company_document_asset_api(request: HttpRequest, asset_kind: str) -> JsonResponse:
    try:
        if asset_kind not in ASSET_FIELDS:
            raise ValidationError({"asset": "Unsupported document branding asset."})
        if not membership_has_capability(request.company_membership, Capability.MANAGE_SETTINGS):
            raise PermissionDenied("Your role cannot manage company settings.")
        settings = company_settings(request.company)
        field_name = ASSET_FIELDS[asset_kind]
        field = getattr(settings, field_name)
        before_name = field.name if field else ""
        if request.method == "POST":
            uploaded = request.FILES.get("file")
            if uploaded is None:
                raise ValidationError({"file": "Choose an image to upload."})
            _validate_image_signature(uploaded)
            setattr(settings, field_name, uploaded)
            settings.save(update_fields=(field_name, "updated_at"))
            action = "company.document_asset.updated"
        else:
            setattr(settings, field_name, "")
            settings.save(update_fields=(field_name, "updated_at"))
            action = "company.document_asset.cleared"
        record_audit_event(
            company=request.company, area=AuditArea.CORE, action=action,
            object_type="CompanySettings", object_id=settings.pk, object_label=f"{asset_kind} branding",
            actor_membership=request.company_membership,
            before={"asset_kind": asset_kind, "storage_name": before_name},
            after={"asset_kind": asset_kind, "storage_name": getattr(settings, field_name).name if getattr(settings, field_name) else ""},
            request=request,
        )
        return JsonResponse({"ok": True, "settings": _serialize(request, settings)})
    except (PermissionDenied, ValidationError) as exc:
        if isinstance(exc, PermissionDenied):
            return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
        return JsonResponse({"ok": False, "errors": _errors(exc)}, status=400)


@require_http_methods(["GET"])
@api_company_required
def company_document_asset_file(request: HttpRequest, asset_kind: str):
    if asset_kind not in ASSET_FIELDS:
        raise Http404
    settings = company_settings(request.company)
    file_field = getattr(settings, ASSET_FIELDS[asset_kind])
    if not file_field or not file_field.name:
        raise Http404
    content_type = mimetypes.guess_type(file_field.name)[0] or "application/octet-stream"
    response = FileResponse(file_field.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{Path(file_field.name).name}"'
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
