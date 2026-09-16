from __future__ import annotations

import json

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .access_catalog import AccessPermission
from .access_profiles import (create_access_profile, delete_unused_access_profile, permission_catalog, serialize_access_profile, update_access_profile)
from .access_history import access_history_page, user_access_history
from .access_policy import membership_has_permission
from .api_permissions import api_company_required
from .models import AccessProfile, CompanyMembership
from .user_management import (
    SCOPE_RESULT_LIMIT,
    create_managed_user,
    delete_unused_managed_user,
    managed_user_detail,
    reset_managed_user_password,
    restore_managed_user_access,
    serialize_user_membership,
    set_managed_user_active,
    update_managed_user,
    user_membership_page,
)


def _json_body(request: HttpRequest) -> dict[str, object]:
    if request.content_type != "application/json":
        raise ValidationError({"__all__": "Content-Type must be application/json."})
    try:
        value = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationError({"__all__": "Request body is not valid JSON."}) from exc
    if not isinstance(value, dict):
        raise ValidationError({"__all__": "JSON request body must be an object."})
    return value


def _error(exc: Exception) -> JsonResponse:
    if isinstance(exc, ValidationError):
        if hasattr(exc, "message_dict"):
            errors = {key: [str(item) for item in values] for key, values in exc.message_dict.items()}
        else:
            errors = {"__all__": [str(item) for item in exc.messages]}
        return JsonResponse({"ok": False, "errors": errors}, status=400)
    if isinstance(exc, ObjectDoesNotExist):
        return JsonResponse({"ok": False, "errors": {"__all__": ["User access record was not found."]}}, status=404)
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    if isinstance(exc, IntegrityError):
        return JsonResponse({"ok": False, "errors": {"__all__": ["The request conflicts with an existing user or access record."]}}, status=409)
    raise exc


def _require(membership, permission: AccessPermission) -> None:
    if not membership_has_permission(membership, permission):
        raise PermissionDenied("Your access profile does not allow this User Management action.")


@require_http_methods(["GET", "POST"])
@api_company_required
def access_users_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            _require(request.company_membership, AccessPermission.ACCESS_USERS_VIEW)
            page = user_membership_page(
                company=request.company,
                query=request.GET.get("q", ""),
                status=request.GET.get("status", "all"),
                page=request.GET.get("page", 1),
                page_size=request.GET.get("page_size", 25),
            )
            return JsonResponse({"ok": True, "users": page})
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        membership = create_managed_user(
            actor_membership=request.company_membership,
            payload=_json_body(request),
            request=request,
        )
        membership = managed_user_detail(company=request.company, membership_id=membership.pk)
        return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)}, status=201)
    except Exception as exc:
        return _error(exc)


@require_http_methods(["GET", "PATCH", "DELETE"])
@api_company_required
def access_user_detail_api(request: HttpRequest, membership_id) -> JsonResponse:
    try:
        if request.method == "GET":
            _require(request.company_membership, AccessPermission.ACCESS_USERS_VIEW)
            membership = managed_user_detail(company=request.company, membership_id=membership_id)
            return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)})
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        body = _json_body(request)
        if request.method == "DELETE":
            delete_unused_managed_user(
                actor_membership=request.company_membership,
                membership_id=membership_id,
                confirmation=str(body.get("confirmation") or ""),
                request=request,
            )
            return JsonResponse({"ok": True, "deleted": True})
        membership = update_managed_user(
            actor_membership=request.company_membership,
            membership_id=membership_id,
            payload=body,
            request=request,
        )
        membership = managed_user_detail(company=request.company, membership_id=membership.pk)
        return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)})
    except Exception as exc:
        return _error(exc)


@require_POST
@api_company_required
def access_user_status_api(request: HttpRequest, membership_id) -> JsonResponse:
    try:
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        body = _json_body(request)
        if not isinstance(body.get("active"), bool):
            raise ValidationError({"active": "Active must be true or false."})
        membership = set_managed_user_active(
            actor_membership=request.company_membership,
            membership_id=membership_id,
            is_active=bool(body["active"]),
            request=request,
        )
        membership = managed_user_detail(company=request.company, membership_id=membership.pk)
        return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)})
    except Exception as exc:
        return _error(exc)


@require_POST
@api_company_required
def access_user_password_reset_api(request: HttpRequest, membership_id) -> JsonResponse:
    try:
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        body = _json_body(request)
        membership = reset_managed_user_password(
            actor_membership=request.company_membership,
            membership_id=membership_id,
            temporary_password=str(body.get("temporaryPassword") or ""),
            request=request,
        )
        membership = managed_user_detail(company=request.company, membership_id=membership.pk)
        return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)})
    except Exception as exc:
        return _error(exc)


@require_http_methods(["GET", "POST"])
@api_company_required
def access_profiles_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            if not (
                membership_has_permission(request.company_membership, AccessPermission.ACCESS_PROFILES_VIEW)
                or membership_has_permission(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
            ):
                raise PermissionDenied("Your access profile cannot view access profiles.")
            profiles = (
                AccessProfile.objects.filter(company=request.company)
                .prefetch_related("permission_grants")
                .order_by("-is_system", "name", "key")
            )
            return JsonResponse({
                "ok": True,
                "profiles": [serialize_access_profile(profile) for profile in profiles],
                "permissionCatalog": permission_catalog(),
                "canManage": membership_has_permission(request.company_membership, AccessPermission.ACCESS_PROFILES_MANAGE),
            })
        profile = create_access_profile(
            actor_membership=request.company_membership, payload=_json_body(request), request=request
        )
        return JsonResponse({"ok": True, "profile": serialize_access_profile(profile)}, status=201)
    except Exception as exc:
        return _error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_company_required
def access_profile_detail_api(request: HttpRequest, profile_id) -> JsonResponse:
    try:
        body = _json_body(request)
        if request.method == "DELETE":
            delete_unused_access_profile(
                actor_membership=request.company_membership, profile_id=profile_id,
                confirmation=str(body.get("confirmation") or ""), request=request,
            )
            return JsonResponse({"ok": True, "deleted": True})
        profile = update_access_profile(
            actor_membership=request.company_membership, profile_id=profile_id, payload=body, request=request
        )
        return JsonResponse({"ok": True, "profile": serialize_access_profile(profile)})
    except Exception as exc:
        return _error(exc)


@require_GET
@api_company_required
def access_scope_lookup_api(request: HttpRequest) -> JsonResponse:
    try:
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        scope_type = request.GET.get("type", "").strip().lower()
        q = request.GET.get("q", "").strip()
        if q and len(q) < 2:
            raise ValidationError({"q": "Enter at least 2 characters to search scope records."})
        if scope_type == "projects":
            from apps.projects.models import Project
            qs = Project.objects.filter(company=request.company, status=Project.Status.ACTIVE, deleted_at__isnull=True)
            if q:
                qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(client_name__icontains=q))
            rows = [{"id": str(row.pk), "code": row.code, "name": row.name, "meta": row.client_name} for row in qs.order_by("code")[:SCOPE_RESULT_LIMIT]]
        elif scope_type == "branches":
            from apps.internal_payroll.models import Branch
            qs = Branch.objects.filter(company=request.company, is_active=True, archived_at__isnull=True, deleted_at__isnull=True)
            if q:
                qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(location__icontains=q))
            rows = [{"id": str(row.pk), "code": row.code, "name": row.name, "meta": row.get_kind_display()} for row in qs.order_by("code")[:SCOPE_RESULT_LIMIT]]
        elif scope_type == "inventory_locations":
            from apps.inventory.models import InventoryLocation
            qs = InventoryLocation.objects.filter(company=request.company, is_active=True, archived_at__isnull=True, deleted_at__isnull=True)
            if q:
                qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
            rows = [{"id": str(row.pk), "code": row.code, "name": row.name, "meta": row.get_location_type_display()} for row in qs.order_by("code")[:SCOPE_RESULT_LIMIT]]
        else:
            raise ValidationError({"type": "Type must be projects, branches, or inventory_locations."})
        return JsonResponse({"ok": True, "type": scope_type, "rows": rows, "limit": SCOPE_RESULT_LIMIT})
    except Exception as exc:
        return _error(exc)


@require_GET
@api_company_required
def access_audit_api(request: HttpRequest) -> JsonResponse:
    try:
        payload = access_history_page(
            actor_membership=request.company_membership,
            query=request.GET.get("q", ""),
            target=request.GET.get("target", "all"),
            page=request.GET.get("page", 1),
            page_size=request.GET.get("page_size", 25),
        )
        return JsonResponse({"ok": True, "audit": payload})
    except Exception as exc:
        return _error(exc)


@require_GET
@api_company_required
def access_user_history_api(request: HttpRequest, membership_id) -> JsonResponse:
    try:
        payload = user_access_history(
            actor_membership=request.company_membership,
            membership_id=membership_id,
            page=request.GET.get("page", 1),
            page_size=request.GET.get("page_size", 25),
        )
        return JsonResponse({"ok": True, "history": payload})
    except Exception as exc:
        return _error(exc)


@require_POST
@api_company_required
def access_user_restore_api(request: HttpRequest, membership_id) -> JsonResponse:
    try:
        _require(request.company_membership, AccessPermission.ACCESS_USERS_MANAGE)
        _require(request.company_membership, AccessPermission.ACCESS_AUDIT_VIEW)
        body = _json_body(request)
        membership = restore_managed_user_access(
            actor_membership=request.company_membership,
            membership_id=membership_id,
            event_id=body.get("eventId"),
            confirmation=str(body.get("confirmation") or ""),
            request=request,
        )
        membership = managed_user_detail(company=request.company, membership_id=membership.pk)
        return JsonResponse({"ok": True, "user": serialize_user_membership(membership, detail=True)})
    except Exception as exc:
        return _error(exc)
