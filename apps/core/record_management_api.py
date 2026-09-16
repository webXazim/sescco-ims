from __future__ import annotations

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET

from apps.accounts.api_permissions import api_company_required
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace
from apps.core.selectors.record_management import record_management_page_context


@require_GET
@api_company_required
def record_management_api(request: HttpRequest) -> JsonResponse:
    try:
        workspace = request.GET.get("workspace", "").strip()
        try:
            workspace_enum = Workspace(workspace)
        except ValueError as exc:
            raise ValidationError({"workspace": "Workspace must be internal or rental."}) from exc
        if workspace_enum not in {Workspace.INTERNAL, Workspace.RENTAL}:
            raise ValidationError({"workspace": "Record Management supports Internal Company or Rental Manpower."})
        if not membership_can_workspace(request.company_membership, workspace_enum):
            raise PermissionDenied("Your access profile cannot access this workspace.")
        bucket = request.GET.get("bucket", "archive").strip().lower()
        required = AccessPermission.SHARED_TRASH_VIEW if bucket == "trash" else AccessPermission.SHARED_ARCHIVE_VIEW
        if not membership_has_permission(request.company_membership, required):
            raise PermissionDenied("Your access profile cannot view Archive / Delete recovery records.")
        payload = record_management_page_context(
            company=request.company,
            workspace=workspace,
            bucket=bucket,
            page=request.GET.get("page", 1),
            page_size=request.GET.get("page_size", 50),
            query=request.GET.get("q", ""),
            membership=request.company_membership,
        )
        return JsonResponse({"ok": True, **payload})
    except PermissionDenied as exc:
        return JsonResponse({"ok": False, "errors": {"__all__": [str(exc)]}}, status=403)
    except (ValidationError, ValueError) as exc:
        if isinstance(exc, ValidationError) and hasattr(exc, "message_dict"):
            errors = {key: [str(item) for item in values] for key, values in exc.message_dict.items()}
        else:
            messages = getattr(exc, "messages", [str(exc)])
            errors = {"__all__": [str(item) for item in messages]}
        return JsonResponse({"ok": False, "errors": errors}, status=400)
