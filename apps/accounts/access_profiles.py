from __future__ import annotations

import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.text import slugify

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from .access_catalog import AccessPermission
from .access_policy import membership_has_permission
from .models import AccessProfile, AccessProfilePermission, CompanyMembership
from .security import bump_profile_user_security_versions, bump_user_security_version


_PERMISSION_VALUES = frozenset(permission.value for permission in AccessPermission)


_ACTION_VIEW_DEPENDENCIES = {
    AccessPermission.PULSE_PROJECTS_VIEW.value: AccessPermission.PULSE_OVERVIEW_VIEW.value,
    AccessPermission.PULSE_TEAM_VIEW.value: AccessPermission.PULSE_PROJECTS_VIEW.value,
    AccessPermission.PULSE_TEAM_MANAGE.value: AccessPermission.PULSE_TEAM_VIEW.value,
    AccessPermission.PULSE_CATEGORIES_VIEW.value: AccessPermission.PULSE_PROJECTS_VIEW.value,
    AccessPermission.PULSE_CATEGORIES_MANAGE.value: AccessPermission.PULSE_CATEGORIES_VIEW.value,
    AccessPermission.PULSE_TASKS_VIEW.value: AccessPermission.PULSE_PROJECTS_VIEW.value,
    AccessPermission.PULSE_TASKS_MANAGE.value: AccessPermission.PULSE_TASKS_VIEW.value,
    AccessPermission.PULSE_PROGRESS_VIEW.value: AccessPermission.PULSE_TASKS_VIEW.value,
    AccessPermission.PULSE_PROGRESS_UPDATE.value: AccessPermission.PULSE_PROGRESS_VIEW.value,
    AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW.value: AccessPermission.PULSE_PROJECTS_VIEW.value,
    AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE.value: AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW.value,
    AccessPermission.PULSE_EXPENSES_VIEW.value: AccessPermission.PULSE_TASKS_VIEW.value,
    AccessPermission.PULSE_EXPENSES_MANAGE.value: AccessPermission.PULSE_EXPENSES_VIEW.value,
    AccessPermission.PULSE_EXPENSES_APPROVE.value: AccessPermission.PULSE_EXPENSES_VIEW.value,
    AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE.value: AccessPermission.PULSE_EXPENSES_VIEW.value,
    AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE.value: AccessPermission.PULSE_EXPENSES_MANAGE.value,
    AccessPermission.PULSE_BUDGETS_VIEW.value: AccessPermission.PULSE_EXPENSES_VIEW.value,
    AccessPermission.PULSE_BUDGETS_MANAGE.value: AccessPermission.PULSE_BUDGETS_VIEW.value,
    AccessPermission.PULSE_BUDGETS_APPROVE.value: AccessPermission.PULSE_BUDGETS_VIEW.value,
    AccessPermission.PULSE_FINANCIALS_VIEW.value: AccessPermission.PULSE_BUDGETS_VIEW.value,
    AccessPermission.PULSE_CONTRACTS_MANAGE.value: AccessPermission.PULSE_FINANCIALS_VIEW.value,
    AccessPermission.PULSE_CONTRACTS_APPROVE.value: AccessPermission.PULSE_FINANCIALS_VIEW.value,
    AccessPermission.PULSE_FORECASTS_MANAGE.value: AccessPermission.PULSE_FINANCIALS_VIEW.value,
    AccessPermission.PULSE_FORECASTS_APPROVE.value: AccessPermission.PULSE_FINANCIALS_VIEW.value,
    AccessPermission.PULSE_REPORTS_VIEW.value: AccessPermission.PULSE_PROJECTS_VIEW.value,
    AccessPermission.PULSE_REPORTS_EXPORT.value: AccessPermission.PULSE_REPORTS_VIEW.value,
    AccessPermission.ACCESS_USERS_MANAGE.value: AccessPermission.ACCESS_USERS_VIEW.value,
    AccessPermission.ACCESS_PROFILES_MANAGE.value: AccessPermission.ACCESS_PROFILES_VIEW.value,
    AccessPermission.SETTINGS_MANAGE.value: AccessPermission.SETTINGS_VIEW.value,
    AccessPermission.SHARED_DOCUMENTS_FINALIZE.value: AccessPermission.SHARED_DOCUMENTS_VIEW.value,
    AccessPermission.SHARED_REPORTS_EXPORT.value: AccessPermission.SHARED_REPORTS_VIEW.value,
    AccessPermission.SHARED_ARCHIVE_MANAGE.value: AccessPermission.SHARED_ARCHIVE_VIEW.value,
    AccessPermission.SHARED_TRASH_MANAGE.value: AccessPermission.SHARED_TRASH_VIEW.value,
    AccessPermission.INVENTORY_STOCK_RECEIVE.value: AccessPermission.INVENTORY_STOCK_VIEW.value,
    AccessPermission.INVENTORY_STOCK_ISSUE.value: AccessPermission.INVENTORY_STOCK_VIEW.value,
    AccessPermission.INVENTORY_STOCK_TRANSFER.value: AccessPermission.INVENTORY_STOCK_VIEW.value,
    AccessPermission.INVENTORY_STOCK_APPROVE.value: AccessPermission.INVENTORY_STOCK_VIEW.value,
    AccessPermission.INVENTORY_STOCK_ADJUST.value: AccessPermission.INVENTORY_STOCK_VIEW.value,
    AccessPermission.INVENTORY_MOVEMENTS_REVERSE.value: AccessPermission.INVENTORY_MOVEMENTS_VIEW.value,
    AccessPermission.INVENTORY_PROJECTS_MANAGE.value: AccessPermission.INVENTORY_PROJECTS_VIEW.value,
    AccessPermission.INVENTORY_SUPPLIERS_MANAGE.value: AccessPermission.INVENTORY_SUPPLIERS_VIEW.value,
    AccessPermission.INVENTORY_LOCATIONS_MANAGE.value: AccessPermission.INVENTORY_LOCATIONS_VIEW.value,
    AccessPermission.INTERNAL_EMPLOYEES_MANAGE.value: AccessPermission.INTERNAL_EMPLOYEES_VIEW.value,
    AccessPermission.INTERNAL_ORGANIZATION_MANAGE.value: AccessPermission.INTERNAL_ORGANIZATION_VIEW.value,
    AccessPermission.INTERNAL_ATTENDANCE_EDIT.value: AccessPermission.INTERNAL_ATTENDANCE_VIEW.value,
    AccessPermission.INTERNAL_ATTENDANCE_SUBMIT.value: AccessPermission.INTERNAL_ATTENDANCE_VIEW.value,
    AccessPermission.INTERNAL_ATTENDANCE_APPROVE.value: AccessPermission.INTERNAL_ATTENDANCE_VIEW.value,
    AccessPermission.INTERNAL_SALARY_SETUP_MANAGE.value: AccessPermission.INTERNAL_SALARY_SETUP_VIEW.value,
    AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE.value: AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW.value,
    AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW.value: AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW.value,
    AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE.value: AccessPermission.INTERNAL_PAYROLL_RUNS_VIEW.value,
    AccessPermission.INTERNAL_ADJUSTMENTS_MANAGE.value: AccessPermission.INTERNAL_ADJUSTMENTS_VIEW.value,
    AccessPermission.INTERNAL_ADJUSTMENTS_APPROVE.value: AccessPermission.INTERNAL_ADJUSTMENTS_VIEW.value,
    AccessPermission.INTERNAL_PAYMENTS_PREPARE.value: AccessPermission.INTERNAL_PAYMENTS_VIEW.value,
    AccessPermission.INTERNAL_PAYMENTS_EXECUTE.value: AccessPermission.INTERNAL_PAYMENTS_VIEW.value,
    AccessPermission.INTERNAL_WPS_EXPORT.value: AccessPermission.INTERNAL_WPS_VIEW.value,
    AccessPermission.INTERNAL_DOCUMENTS_FINALIZE.value: AccessPermission.INTERNAL_DOCUMENTS_VIEW.value,
    AccessPermission.INTERNAL_REPORTS_EXPORT.value: AccessPermission.INTERNAL_REPORTS_VIEW.value,
    AccessPermission.RENTAL_WORKERS_MANAGE.value: AccessPermission.RENTAL_WORKERS_VIEW.value,
    AccessPermission.RENTAL_SUPPLIERS_MANAGE.value: AccessPermission.RENTAL_SUPPLIERS_VIEW.value,
    AccessPermission.RENTAL_ASSIGNMENTS_MANAGE.value: AccessPermission.RENTAL_ASSIGNMENTS_VIEW.value,
    AccessPermission.RENTAL_TIMESHEETS_EDIT.value: AccessPermission.RENTAL_TIMESHEETS_VIEW.value,
    AccessPermission.RENTAL_TIMESHEETS_SUBMIT.value: AccessPermission.RENTAL_TIMESHEETS_VIEW.value,
    AccessPermission.RENTAL_TIMESHEETS_APPROVE.value: AccessPermission.RENTAL_TIMESHEETS_VIEW.value,
    AccessPermission.RENTAL_OVERTIME_EDIT.value: AccessPermission.RENTAL_OVERTIME_VIEW.value,
    AccessPermission.RENTAL_OVERTIME_SUBMIT.value: AccessPermission.RENTAL_OVERTIME_VIEW.value,
    AccessPermission.RENTAL_OVERTIME_APPROVE.value: AccessPermission.RENTAL_OVERTIME_VIEW.value,
    AccessPermission.RENTAL_ADJUSTMENTS_MANAGE.value: AccessPermission.RENTAL_ADJUSTMENTS_VIEW.value,
    AccessPermission.RENTAL_ADJUSTMENTS_APPROVE.value: AccessPermission.RENTAL_ADJUSTMENTS_VIEW.value,
    AccessPermission.RENTAL_SETTLEMENTS_PREPARE.value: AccessPermission.RENTAL_SETTLEMENTS_VIEW.value,
    AccessPermission.RENTAL_SETTLEMENTS_APPROVE.value: AccessPermission.RENTAL_SETTLEMENTS_VIEW.value,
    AccessPermission.RENTAL_PAYMENTS_PREPARE.value: AccessPermission.RENTAL_PAYMENTS_VIEW.value,
    AccessPermission.RENTAL_PAYMENTS_EXECUTE.value: AccessPermission.RENTAL_PAYMENTS_VIEW.value,
    AccessPermission.RENTAL_DOCUMENTS_FINALIZE.value: AccessPermission.RENTAL_DOCUMENTS_VIEW.value,
    AccessPermission.RENTAL_REPORTS_EXPORT.value: AccessPermission.RENTAL_REPORTS_VIEW.value,
    AccessPermission.SOURCING_VENDORS_MANAGE.value: AccessPermission.SOURCING_VENDORS_VIEW.value,
    AccessPermission.SOURCING_MANPOWER_MANAGE.value: AccessPermission.SOURCING_MANPOWER_VIEW.value,
    AccessPermission.SOURCING_SUBCONTRACTORS_MANAGE.value: AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value,
    AccessPermission.SOURCING_MASTERS_MANAGE.value: AccessPermission.SOURCING_MASTERS_VIEW.value,
}


def _require_manage_profiles(actor: CompanyMembership) -> None:
    if not membership_has_permission(actor, AccessPermission.ACCESS_PROFILES_MANAGE):
        raise PermissionDenied("Your access profile cannot manage Access Profiles.")


def _permission_kind(value: str) -> str:
    if value.endswith(".view") or value == AccessPermission.SHARED_SEARCH_USE.value:
        return "view"
    if value.endswith(".manage") or value.endswith(".update") or value.endswith(".edit") or value.endswith(".prepare") or value.endswith(".execute") or value.endswith(".finalize") or value.endswith(".export") or value.endswith(".submit") or value.endswith(".review") or value.endswith(".approve") or value.endswith(".receive") or value.endswith(".issue") or value.endswith(".transfer") or value.endswith(".adjust") or value.endswith(".reverse"):
        return "action"
    return "platform"


def permission_catalog() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for permission in AccessPermission:
        value = permission.value
        prefix = value.split(".", 1)[0]
        category = {
            "access": "Administration",
            "settings": "Administration",
            "inventory": "Inventory Management",
            "internal": "Internal Payroll",
            "rental": "Rental Manpower",
            "sourcing": "Sourcing Directory",
            "pulse": "Project Pulse",
            "shared": "Shared Records",
        }.get(prefix, "Platform")
        label_overrides = {
            AccessPermission.INVENTORY_STOCK_APPROVE.value: "Project Inventory · Approve / Reject",
            AccessPermission.PULSE_OVERVIEW_VIEW.value: "Project Pulse · Overview / View",
            AccessPermission.PULSE_PROJECTS_VIEW.value: "Project Pulse · Projects / View",
            AccessPermission.PULSE_TEAM_VIEW.value: "Project Pulse · Team / View",
            AccessPermission.PULSE_TEAM_MANAGE.value: "Project Pulse · Team / Manage",
            AccessPermission.PULSE_CATEGORIES_VIEW.value: "Project Pulse · Execution Categories / View",
            AccessPermission.PULSE_CATEGORIES_MANAGE.value: "Project Pulse · Execution Categories / Manage",
            AccessPermission.PULSE_TASKS_VIEW.value: "Project Pulse · Scheduled Works / View",
            AccessPermission.PULSE_TASKS_MANAGE.value: "Project Pulse · Scheduled Works / Manage",
            AccessPermission.PULSE_PROGRESS_VIEW.value: "Project Pulse · Execution Progress / View",
            AccessPermission.PULSE_PROGRESS_UPDATE.value: "Project Pulse · Complete / Reopen Work",
            AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW.value: "Project Pulse · Expense Categories / View",
            AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE.value: "Project Pulse · Expense Categories / Manage",
            AccessPermission.PULSE_EXPENSES_VIEW.value: "Project Pulse · Expense Amounts / View",
            AccessPermission.PULSE_EXPENSES_MANAGE.value: "Project Pulse · Expense Records / Manage",
            AccessPermission.PULSE_EXPENSES_APPROVE.value: "Project Pulse · Expenses / Approve or Reject",
            AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE.value: "Project Pulse · Expense Payments / Manage",
            AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE.value: "Project Pulse · Expense Attachments / Upload",
            AccessPermission.PULSE_BUDGETS_VIEW.value: "Project Pulse · Category Budgets / View",
            AccessPermission.PULSE_BUDGETS_MANAGE.value: "Project Pulse · Category Budgets / Propose",
            AccessPermission.PULSE_BUDGETS_APPROVE.value: "Project Pulse · Category Budgets / Approve",
            AccessPermission.PULSE_FINANCIALS_VIEW.value: "Project Pulse · Profit & Contract / View",
            AccessPermission.PULSE_REPORTS_VIEW.value: "Project Pulse · Reports / View",
            AccessPermission.PULSE_REPORTS_EXPORT.value: "Project Pulse · Reports / Export",
            AccessPermission.PULSE_CONTRACTS_MANAGE.value: "Project Pulse · Contract & Variations / Propose",
            AccessPermission.PULSE_CONTRACTS_APPROVE.value: "Project Pulse · Contract & Variations / Approve",
            AccessPermission.PULSE_FORECASTS_MANAGE.value: "Project Pulse · Forecasts / Propose",
            AccessPermission.PULSE_FORECASTS_APPROVE.value: "Project Pulse · Forecasts / Approve",
            AccessPermission.SOURCING_VENDORS_VIEW.value: "Vendor Sourcing · View",
            AccessPermission.SOURCING_VENDORS_MANAGE.value: "Vendor Sourcing · Edit",
            AccessPermission.SOURCING_MANPOWER_VIEW.value: "Manpower Sourcing · View",
            AccessPermission.SOURCING_MANPOWER_MANAGE.value: "Manpower Sourcing · Edit",
            AccessPermission.SOURCING_SUBCONTRACTORS_VIEW.value: "Subcontractor Sourcing · View",
            AccessPermission.SOURCING_SUBCONTRACTORS_MANAGE.value: "Subcontractor Sourcing · Edit",
            AccessPermission.SOURCING_MASTERS_VIEW.value: "Reference Masters · View",
            AccessPermission.SOURCING_MASTERS_MANAGE.value: "Reference Masters · Edit",
            AccessPermission.SOURCING_EXPORT_EXECUTE.value: "Sourcing Data · Export",
        }
        label = label_overrides.get(value, value.replace(".", " · ").replace("_", " ").title())
        rows.append({"code": value, "label": label, "category": category, "kind": _permission_kind(value)})
    return rows


def serialize_access_profile(profile: AccessProfile) -> dict[str, object]:
    grants = getattr(profile, "_prefetched_objects_cache", {}).get("permission_grants")
    permissions = sorted(grant.permission for grant in grants) if grants is not None else sorted(profile.permission_grants.values_list("permission", flat=True))
    return {
        "id": str(profile.pk),
        "key": profile.key,
        "name": profile.name,
        "description": profile.description,
        "system": profile.is_system,
        "active": profile.is_active,
        "owner": bool(profile.is_system and profile.key == "role-owner"),
        "permissions": permissions,
        "assignedUsers": profile.memberships.filter(is_active=True, user__is_active=True).count(),
    }


def _clean_name(value: object) -> str:
    name = " ".join(str(value or "").split())
    if not name:
        raise ValidationError({"name": "Profile name is required."})
    if len(name) > 120:
        raise ValidationError({"name": "Profile name must be 120 characters or fewer."})
    return name


def _clean_description(value: object) -> str:
    description = str(value or "").strip()
    if len(description) > 2000:
        raise ValidationError({"description": "Description is too long."})
    return description


def _clean_permissions(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError({"permissions": "Permissions must be a list."})
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if len(cleaned) != len(set(cleaned)):
        raise ValidationError({"permissions": "Permissions must not contain duplicates."})
    unknown = sorted(set(cleaned) - _PERMISSION_VALUES)
    if unknown:
        raise ValidationError({"permissions": f"Unknown permission: {unknown[0]}."})
    if not cleaned:
        raise ValidationError({"permissions": "Select at least one page or action permission."})
    selected = set(cleaned)
    missing = sorted(
        (action, view)
        for action, view in _ACTION_VIEW_DEPENDENCIES.items()
        if action in selected and view not in selected
    )
    if missing:
        action, view = missing[0]
        raise ValidationError({"permissions": f"{action} requires its page permission {view}."})
    if AccessPermission.SOURCING_EXPORT_EXECUTE.value in selected and not selected.intersection({
        AccessPermission.SOURCING_VENDORS_VIEW.value,
        AccessPermission.SOURCING_MANPOWER_VIEW.value,
        AccessPermission.SOURCING_MASTERS_VIEW.value,
    }):
        raise ValidationError({
            "permissions": "Sourcing export requires at least one Sourcing view permission."
        })
    return sorted(cleaned)


def _snapshot(profile: AccessProfile) -> dict[str, object]:
    return serialize_access_profile(profile)


def _assert_custom_mutable(*, actor: CompanyMembership, profile: AccessProfile) -> None:
    if profile.company_id != actor.company_id:
        raise PermissionDenied("Access Profile belongs to another company.")
    if profile.is_system:
        raise ValidationError("Built-in Access Profiles are immutable. Create a custom profile instead.")
    if actor.access_profile_id == profile.pk:
        raise PermissionDenied("You cannot modify the Access Profile currently granting your own authority.")



def assigned_profile_users(*, actor_membership: CompanyMembership, source_profile_id) -> list[dict[str, object]]:
    """Return the complete company-scoped assignment roster for the clone review."""
    _require_manage_profiles(actor_membership)
    if not membership_has_permission(actor_membership, AccessPermission.ACCESS_USERS_MANAGE):
        raise PermissionDenied("You cannot reassign users without User Management permission.")
    source = AccessProfile.objects.get(
        pk=source_profile_id, company=actor_membership.company, is_system=True, is_active=True
    )
    if source.key == "role-owner":
        raise PermissionDenied("Company Owner profiles cannot be bulk-cloned or reassigned.")
    members = CompanyMembership.objects.filter(
        company=actor_membership.company, access_profile=source
    ).select_related("user").order_by("user__username", "pk")
    return [
        {
            "membershipId": str(member.pk),
            "displayName": member.user.display_name,
            "username": member.user.username,
            "email": member.user.email,
            "active": bool(member.is_active and member.user.is_active),
            "isSelf": member.pk == actor_membership.pk,
        }
        for member in members
    ]


def _requested_profile_reassignments(*, actor: CompanyMembership, payload: dict[str, object]):
    """Validate the intended membership moves before creating a new profile.

    The source membership set is locked and rechecked at commit time so a stale
    browser selection never moves a different person's authority.
    """
    source_id = payload.get("sourceProfileId")
    mode = payload.get("assignmentMode", "none")
    if mode not in ("none", "selected", "all"):
        raise ValidationError({"assignmentMode": "Choose keep, selected users or all users."})
    if not source_id:
        if mode != "none" or "membershipIds" in payload or "expectedMembershipIds" in payload:
            raise ValidationError({"sourceProfileId": "Select a built-in source profile to move users."})
        return None, [], "none"
    try:
        source = AccessProfile.objects.select_for_update().get(
            pk=source_id, company=actor.company, is_system=True, is_active=True
        )
    except (AccessProfile.DoesNotExist, ValueError, ValidationError) as exc:
        raise ValidationError({"sourceProfileId": "Source profile is no longer available."}) from exc
    if source.key == "role-owner":
        raise PermissionDenied("Company Owner profiles cannot be cloned for reassignment.")
    if mode == "none":
        if payload.get("membershipIds") or payload.get("expectedMembershipIds"):
            raise ValidationError({"membershipIds": "Keep mode does not accept selected users."})
        return source, [], mode
    if not membership_has_permission(actor, AccessPermission.ACCESS_USERS_MANAGE):
        raise PermissionDenied("You cannot reassign users without User Management permission.")
    requested = payload.get("membershipIds", [])
    expected = payload.get("expectedMembershipIds", [])
    if not isinstance(requested, list) or not isinstance(expected, list):
        raise ValidationError({"membershipIds": "User selections must be lists."})
    if mode == "selected" and (not requested or expected):
        raise ValidationError({"membershipIds": "Select one or more source-profile users."})
    if mode == "all" and (requested or not expected):
        raise ValidationError({"expectedMembershipIds": "Review all assigned users before confirming."})
    identifiers = requested if mode == "selected" else expected
    if len(identifiers) != len(set(map(str, identifiers))) or not all(isinstance(v, str) for v in identifiers):
        raise ValidationError({"membershipIds": "Duplicate or invalid user selection."})
    try:
        ids = {uuid.UUID(v) for v in identifiers}
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({"membershipIds": "One or more user IDs are invalid."}) from exc
    if len(ids) != len(identifiers):
        raise ValidationError({"membershipIds": "Duplicate user selection."})
    source_members = list(CompanyMembership.objects.select_for_update().filter(
        company=actor.company, access_profile=source
    ).select_related("access_profile", "user").order_by("pk"))
    if mode == "all":
        if {member.pk for member in source_members} != ids:
            raise ValidationError({"expectedMembershipIds": "Source-profile assignments changed. Review the users and try again."})
        chosen = source_members
    else:
        chosen = [member for member in source_members if member.pk in ids]
        if len(chosen) != len(ids):
            raise ValidationError({"membershipIds": "Selected users have changed profiles. Review and try again."})
    if any(member.pk == actor.pk for member in chosen):
        raise PermissionDenied("You cannot change your own Access Profile.")
    return source, chosen, mode


@transaction.atomic
def create_access_profile(*, actor_membership: CompanyMembership, payload: dict[str, object], request=None) -> AccessProfile:
    _require_manage_profiles(actor_membership)
    name = _clean_name(payload.get("name"))
    description = _clean_description(payload.get("description"))
    permissions = _clean_permissions(payload.get("permissions"))
    source, moved_members, assignment_mode = _requested_profile_reassignments(actor=actor_membership, payload=payload)
    base = slugify(name)[:48] or "custom"
    key = f"custom-{base}-{uuid.uuid4().hex[:8]}"
    profile = AccessProfile.objects.create(
        company=actor_membership.company,
        key=key,
        name=name,
        description=description,
        is_system=False,
        is_active=True,
    )
    AccessProfilePermission.objects.bulk_create([
        AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
    ])
    profile = AccessProfile.objects.prefetch_related("permission_grants").get(pk=profile.pk)
    # Keep full before/after access snapshots so Access History recovery can
    # restore these bulk assignments just like individual User Management edits.
    from .user_management import _identity_snapshot

    # User assignment and profile creation are one atomic operation. A failed
    # membership update or audit event rolls back the entire new profile.
    for member in moved_members:
        before = _identity_snapshot(member)
        member.access_profile = profile
        member.role = "custom"  # Compatibility classification, never an authority grant.
        member.save(update_fields=("access_profile", "role", "updated_at"))
        bump_user_security_version(member.user_id)
        record_audit_event(
            company=profile.company,
            area=AuditArea.ACCESS,
            action="access.user.updated",
            object_type="accounts.CompanyMembership",
            object_id=member.pk,
            object_label=member.user.display_name,
            actor_membership=actor_membership,
            before=before,
            after=_identity_snapshot(member),
            metadata={"profile_clone_user_reassignment": True, "source_profile_id": str(source.pk)},
            request=request,
        )
    record_audit_event(
        company=profile.company,
        area=AuditArea.ACCESS,
        action="access.profile.created",
        object_type="accounts.AccessProfile",
        object_id=profile.pk,
        object_label=profile.name,
        actor_membership=actor_membership,
        after=_snapshot(profile),
        metadata={"source_profile_id": str(source.pk) if source else None, "assignment_mode": assignment_mode, "reassigned_users": len(moved_members)},
        request=request,
    )
    return profile


@transaction.atomic
def update_access_profile(*, actor_membership: CompanyMembership, profile_id, payload: dict[str, object], request=None) -> AccessProfile:
    _require_manage_profiles(actor_membership)
    profile = AccessProfile.objects.select_for_update().prefetch_related("permission_grants").get(
        pk=profile_id, company=actor_membership.company
    )
    _assert_custom_mutable(actor=actor_membership, profile=profile)
    before = _snapshot(profile)
    if "name" in payload:
        profile.name = _clean_name(payload.get("name"))
    if "description" in payload:
        profile.description = _clean_description(payload.get("description"))
    if "active" in payload:
        requested_active = payload.get("active")
        if not isinstance(requested_active, bool):
            raise ValidationError({"active": "Active must be true or false."})
        if not requested_active and profile.memberships.filter(is_active=True, user__is_active=True).exists():
            raise ValidationError("Reassign or deactivate users before deactivating this Access Profile.")
        profile.is_active = requested_active
    profile.save()
    if "permissions" in payload:
        permissions = _clean_permissions(payload.get("permissions"))
        profile.permission_grants.all().delete()
        AccessProfilePermission.objects.bulk_create([
            AccessProfilePermission(profile=profile, permission=permission) for permission in permissions
        ])
    if "permissions" in payload or "active" in payload:
        bump_profile_user_security_versions(profile)
    profile = AccessProfile.objects.prefetch_related("permission_grants").get(pk=profile.pk)
    record_audit_event(
        company=profile.company,
        area=AuditArea.ACCESS,
        action="access.profile.updated",
        object_type="accounts.AccessProfile",
        object_id=profile.pk,
        object_label=profile.name,
        actor_membership=actor_membership,
        before=before,
        after=_snapshot(profile),
        request=request,
    )
    return profile


@transaction.atomic
def delete_unused_access_profile(*, actor_membership: CompanyMembership, profile_id, confirmation: str, request=None) -> None:
    _require_manage_profiles(actor_membership)
    profile = AccessProfile.objects.select_for_update().prefetch_related("permission_grants").get(
        pk=profile_id, company=actor_membership.company
    )
    _assert_custom_mutable(actor=actor_membership, profile=profile)
    if profile.memberships.exists():
        raise ValidationError("Assigned Access Profiles cannot be deleted; reassign every user first.")
    if str(confirmation or "").strip() != profile.name:
        raise ValidationError({"confirmation": "Type the Access Profile name exactly to confirm deletion."})
    before = _snapshot(profile)
    profile_id_text = str(profile.pk)
    profile_name = profile.name
    profile.delete()
    record_audit_event(
        company=actor_membership.company,
        area=AuditArea.ACCESS,
        action="access.profile.deleted",
        object_type="accounts.AccessProfile",
        object_id=profile_id_text,
        object_label=profile_name,
        actor_membership=actor_membership,
        before=before,
        metadata={"guarded_unused_profile_delete": True},
        request=request,
    )
