from __future__ import annotations

from typing import Any

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db.models import Q

from apps.core.models import AuditArea, AuditEvent

from .access_catalog import AccessPermission
from .access_policy import membership_has_permission
from .models import CompanyMembership


ACCESS_AUDIT_PAGE_SIZES = frozenset({25, 50, 100})
_RESTORABLE_USER_ACTIONS = frozenset({
    "access.user.updated",
    "access.user.activated",
    "access.user.deactivated",
    "access.user.access_restored",
})


def _require_audit_view(actor: CompanyMembership) -> None:
    if not membership_has_permission(actor, AccessPermission.ACCESS_AUDIT_VIEW):
        raise PermissionDenied("Your access profile cannot view Access History.")


def _page_values(page: object, page_size: object) -> tuple[int, int]:
    try:
        number = max(1, int(page))
        size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"page": "Page and page size must be integers."}) from exc
    if size not in ACCESS_AUDIT_PAGE_SIZES:
        raise ValidationError({"pageSize": "Page size must be 25, 50, or 100."})
    return number, size


def _safe_dict(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    # The Access ledger never intentionally stores plaintext credentials. Keep a
    # final API boundary guard anyway so a future audit producer cannot expose one.
    blocked = {"password", "temporarypassword", "temporarypasswordvalue", "secret", "token", "authorization"}
    output: dict[str, Any] = {}
    for key, item in value.items():
        normalized = str(key).replace("-", "").replace("_", "").lower()
        if normalized in blocked:
            output[str(key)] = "[redacted]"
        elif isinstance(item, dict):
            output[str(key)] = _safe_dict(item)
        elif isinstance(item, list):
            output[str(key)] = [(_safe_dict(part) if isinstance(part, dict) else part) for part in item]
        else:
            output[str(key)] = item
    return output


def _scope_text(snapshot: dict[str, Any], prefix: str) -> str:
    scopes = snapshot.get("scopes") if isinstance(snapshot.get("scopes"), dict) else {}
    mode = str(scopes.get(f"{prefix}Mode") or "")
    ids = scopes.get(f"{prefix}Ids") if isinstance(scopes.get(f"{prefix}Ids"), list) else []
    if mode == "selected":
        return f"{len(ids)} selected"
    if mode == "none":
        return "None"
    if mode == "all":
        return "All"
    return "—"


def _change_rows(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []

    def add(label: str, left: object, right: object) -> None:
        if left == right:
            return
        changes.append({
            "field": label,
            "before": "—" if left in (None, "") else str(left),
            "after": "—" if right in (None, "") else str(right),
        })

    add("Username", before.get("username"), after.get("username"))
    add("Email", before.get("email"), after.get("email"))
    add("Access Profile", before.get("accessProfileKey") or before.get("key"), after.get("accessProfileKey") or after.get("key"))
    add("Access status", before.get("accessActive"), after.get("accessActive"))
    add("Account status", before.get("accountActive"), after.get("accountActive"))
    if "mustChangePassword" in before or "mustChangePassword" in after:
        add("Password change required", before.get("mustChangePassword"), after.get("mustChangePassword"))

    before_permissions = before.get("permissions") if isinstance(before.get("permissions"), list) else None
    after_permissions = after.get("permissions") if isinstance(after.get("permissions"), list) else None
    if before_permissions is not None or after_permissions is not None:
        add("Permissions", len(before_permissions or []), len(after_permissions or []))
    if "active" in before or "active" in after:
        add("Profile status", before.get("active"), after.get("active"))
    if "name" in before or "name" in after:
        add("Profile name", before.get("name"), after.get("name"))

    for prefix, label in (("project", "Project scope"), ("branch", "Branch scope"), ("inventoryLocation", "Inventory scope")):
        left = _scope_text(before, prefix)
        right = _scope_text(after, prefix)
        if left != "—" or right != "—":
            add(label, left, right)
    return changes[:10]


def serialize_access_event(event: AuditEvent, *, restorable_before: bool = False) -> dict[str, object]:
    before = _safe_dict(event.before)
    after = _safe_dict(event.after)
    metadata = _safe_dict(event.metadata)
    return {
        "id": str(event.pk),
        "date": event.created_at.isoformat(),
        "action": event.action,
        "actor": event.actor_display_name or event.actor_username or "System",
        "actorUsername": event.actor_username,
        "actorRole": event.actor_role,
        "targetType": event.object_type,
        "targetId": event.object_id,
        "target": event.object_label or event.object_id,
        "requestId": event.request_id or "",
        "before": before,
        "after": after,
        "changes": _change_rows(before, after),
        "metadata": metadata,
        "restorableBefore": bool(restorable_before),
    }


def access_history_page(
    *, actor_membership: CompanyMembership, query: str = "", target: str = "all", page: object = 1, page_size: object = 25
) -> dict[str, object]:
    _require_audit_view(actor_membership)
    number, size = _page_values(page, page_size)
    q = str(query or "").strip()
    if q and len(q) < 2:
        raise ValidationError({"q": "Enter at least 2 characters to search Access History."})
    target_value = str(target or "all").strip().lower()
    qs = AuditEvent.objects.filter(company=actor_membership.company, area=AuditArea.ACCESS)
    if target_value == "users":
        qs = qs.filter(object_type__in=("accounts.CompanyMembership", "accounts.User"))
    elif target_value == "profiles":
        qs = qs.filter(object_type="accounts.AccessProfile")
    elif target_value != "all":
        raise ValidationError({"target": "Target must be all, users, or profiles."})
    if q:
        qs = qs.filter(
            Q(action__icontains=q) | Q(object_label__icontains=q) | Q(object_id__icontains=q)
            | Q(actor_display_name__icontains=q) | Q(actor_username__icontains=q)
        )
    qs = qs.order_by("-created_at", "-id")
    offset = (number - 1) * size
    rows = list(qs[offset: offset + size + 1])
    has_next = len(rows) > size
    rows = rows[:size]
    return {
        "rows": [serialize_access_event(row) for row in rows],
        "page": number,
        "pageSize": size,
        "hasNext": has_next,
        "hasPrevious": number > 1,
        "query": q,
        "target": target_value,
    }


def user_access_history(
    *, actor_membership: CompanyMembership, membership_id, page: object = 1, page_size: object = 25
) -> dict[str, object]:
    _require_audit_view(actor_membership)
    number, size = _page_values(page, page_size)
    try:
        target = CompanyMembership.objects.select_related("user").get(
            pk=membership_id, company=actor_membership.company
        )
    except (CompanyMembership.DoesNotExist, ValueError) as exc:
        raise ObjectDoesNotExist("User access record was not found.") from exc

    qs = AuditEvent.objects.filter(company=actor_membership.company, area=AuditArea.ACCESS).filter(
        Q(object_type="accounts.CompanyMembership", object_id=str(target.pk))
        | Q(object_type="accounts.User", object_id=str(target.user_id))
    ).order_by("-created_at", "-id")
    offset = (number - 1) * size
    rows = list(qs[offset: offset + size + 1])
    has_next = len(rows) > size
    rows = rows[:size]
    payload = []
    for row in rows:
        before = row.before if isinstance(row.before, dict) else {}
        restorable = bool(
            row.object_type == "accounts.CompanyMembership"
            and row.action in _RESTORABLE_USER_ACTIONS
            and before.get("accessProfileId")
            and isinstance(before.get("scopes"), dict)
            and isinstance(before.get("accessActive"), bool)
        )
        payload.append(serialize_access_event(row, restorable_before=restorable))
    return {
        "rows": payload,
        "page": number,
        "pageSize": size,
        "hasNext": has_next,
        "hasPrevious": number > 1,
        "membershipId": str(target.pk),
        "username": target.user.username,
    }
