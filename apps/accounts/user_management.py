from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.contrib.auth import password_validation
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.models import AuditArea, AuditEvent
from apps.core.services.audit import record_audit_event

from .access_catalog import AccessPermission, system_profile_key_for_role
from .access_policy import membership_has_permission
from .models import (
    AccessProfile,
    CompanyMembership,
    MembershipBranchScope,
    MembershipInventoryLocationScope,
    MembershipProjectScope,
    ScopeMode,
    User,
)
from .roles import AccessRole
from .security import bump_user_security_version


USER_PAGE_SIZES = frozenset({25, 50, 100})
SCOPE_RESULT_LIMIT = 25


def _require_manage_users(actor: CompanyMembership) -> None:
    if not membership_has_permission(actor, AccessPermission.ACCESS_USERS_MANAGE):
        raise PermissionDenied("Your access profile cannot manage users.")


def _is_owner_profile(profile: AccessProfile | None) -> bool:
    return bool(
        profile
        and profile.is_system
        and profile.is_active
        and profile.key == system_profile_key_for_role(AccessRole.OWNER)
    )


def _actor_is_owner(actor: CompanyMembership) -> bool:
    return _is_owner_profile(actor.access_profile)


def _classification_for_profile(profile: AccessProfile) -> str:
    if profile.is_system and profile.key.startswith("role-"):
        candidate = profile.key[5:]
        if candidate in AccessRole.values and candidate != AccessRole.CUSTOM:
            return candidate
    return AccessRole.CUSTOM


def _clean_identity(*, username: object, email: object, first_name: object, last_name: object) -> dict[str, str]:
    values = {
        "username": str(username or "").strip(),
        "email": str(email or "").strip().lower(),
        "first_name": " ".join(str(first_name or "").split()),
        "last_name": " ".join(str(last_name or "").split()),
    }
    errors: dict[str, str] = {}
    if not values["username"]:
        errors["username"] = "Username is required."
    if not values["email"]:
        errors["email"] = "Email is required."
    if errors:
        raise ValidationError(errors)
    return values


def _validate_identity_uniqueness(values: dict[str, str], *, exclude_user_id=None) -> None:
    username_qs = User.objects.filter(username__iexact=values["username"])
    email_qs = User.objects.filter(email__iexact=values["email"])
    if exclude_user_id:
        username_qs = username_qs.exclude(pk=exclude_user_id)
        email_qs = email_qs.exclude(pk=exclude_user_id)
    errors: dict[str, str] = {}
    if username_qs.exists():
        errors["username"] = "A user with this username already exists."
    if email_qs.exists():
        errors["email"] = "A user with this email already exists."
    if errors:
        raise ValidationError(errors)


def _profile_for_assignment(*, company, profile_id, actor: CompanyMembership) -> AccessProfile:
    try:
        profile = AccessProfile.objects.select_for_update().get(pk=profile_id, company=company, is_active=True)
    except (AccessProfile.DoesNotExist, ValueError) as exc:
        raise ValidationError({"accessProfileId": "Choose an active access profile from this company."}) from exc
    if _is_owner_profile(profile) and not _actor_is_owner(actor):
        raise PermissionDenied("Only a Company Owner can assign the Company Owner access profile.")
    return profile


def _scope_mode(value: object, field: str) -> str:
    normalized = str(value or ScopeMode.ALL).strip().lower()
    if normalized not in ScopeMode.values:
        raise ValidationError({field: "Scope mode must be all, selected, or none."})
    return normalized


def _id_list(value: object, field: str) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValidationError({field: "Provide a list of record IDs."})
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    if len(cleaned) != len(set(cleaned)):
        raise ValidationError({field: "Scope IDs must not contain duplicates."})
    return cleaned


@dataclass(frozen=True, slots=True)
class ScopeAssignment:
    project_mode: str
    project_ids: tuple[str, ...]
    branch_mode: str
    branch_ids: tuple[str, ...]
    location_mode: str
    location_ids: tuple[str, ...]


def parse_scope_assignment(payload: dict[str, object] | None) -> ScopeAssignment:
    payload = payload or {}
    project_mode = _scope_mode(payload.get("projectMode", ScopeMode.ALL), "projectMode")
    branch_mode = _scope_mode(payload.get("branchMode", ScopeMode.ALL), "branchMode")
    location_mode = _scope_mode(payload.get("inventoryLocationMode", ScopeMode.ALL), "inventoryLocationMode")
    project_ids = _id_list(payload.get("projectIds", []), "projectIds")
    branch_ids = _id_list(payload.get("branchIds", []), "branchIds")
    location_ids = _id_list(payload.get("inventoryLocationIds", []), "inventoryLocationIds")
    for mode, ids, field in (
        (project_mode, project_ids, "projectIds"),
        (branch_mode, branch_ids, "branchIds"),
        (location_mode, location_ids, "inventoryLocationIds"),
    ):
        if mode == ScopeMode.SELECTED and not ids:
            raise ValidationError({field: "Select at least one record when scope mode is selected."})
        if mode != ScopeMode.SELECTED and ids:
            raise ValidationError({field: "Scope IDs are allowed only when scope mode is selected."})
    return ScopeAssignment(
        project_mode, tuple(project_ids), branch_mode, tuple(branch_ids), location_mode, tuple(location_ids)
    )


def _apply_scope_assignment(*, membership: CompanyMembership, assignment: ScopeAssignment) -> None:
    from apps.internal_payroll.models import Branch
    from apps.inventory.models import InventoryLocation
    from apps.projects.models import Project

    try:
        project_rows = list(Project.objects.filter(
            company=membership.company, status=Project.Status.ACTIVE, deleted_at__isnull=True,
            pk__in=assignment.project_ids,
        ))
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError({"projectIds": "One or more project IDs are invalid."}) from exc
    try:
        branch_rows = list(Branch.objects.filter(
            company=membership.company, is_active=True, archived_at__isnull=True, deleted_at__isnull=True,
            pk__in=assignment.branch_ids,
        ))
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError({"branchIds": "One or more branch/office IDs are invalid."}) from exc
    try:
        location_rows = list(InventoryLocation.objects.filter(
            company=membership.company, is_active=True, archived_at__isnull=True, deleted_at__isnull=True,
            pk__in=assignment.location_ids,
        ))
    except (TypeError, ValueError, ValidationError) as exc:
        raise ValidationError({"inventoryLocationIds": "One or more inventory location IDs are invalid."}) from exc
    errors: dict[str, str] = {}
    if len(project_rows) != len(assignment.project_ids):
        errors["projectIds"] = "One or more selected projects are unavailable in this company."
    if len(branch_rows) != len(assignment.branch_ids):
        errors["branchIds"] = "One or more selected branches/offices are unavailable in this company."
    if len(location_rows) != len(assignment.location_ids):
        errors["inventoryLocationIds"] = "One or more selected inventory locations are unavailable in this company."
    if errors:
        raise ValidationError(errors)

    membership.project_scope_mode = assignment.project_mode
    membership.branch_scope_mode = assignment.branch_mode
    membership.inventory_location_scope_mode = assignment.location_mode
    membership.save(update_fields=(
        "project_scope_mode", "branch_scope_mode", "inventory_location_scope_mode", "updated_at"
    ))
    membership.project_scopes.all().delete()
    membership.branch_scopes.all().delete()
    membership.inventory_location_scopes.all().delete()
    MembershipProjectScope.objects.bulk_create(
        [MembershipProjectScope(membership=membership, project=row) for row in project_rows], batch_size=250
    )
    MembershipBranchScope.objects.bulk_create(
        [MembershipBranchScope(membership=membership, branch=row) for row in branch_rows], batch_size=250
    )
    MembershipInventoryLocationScope.objects.bulk_create(
        [MembershipInventoryLocationScope(membership=membership, inventory_location=row) for row in location_rows], batch_size=250
    )


def _scope_snapshot(membership: CompanyMembership) -> dict[str, object]:
    return {
        "projectMode": membership.project_scope_mode,
        "projectIds": sorted(str(value) for value in membership.project_scopes.values_list("project_id", flat=True)),
        "branchMode": membership.branch_scope_mode,
        "branchIds": sorted(str(value) for value in membership.branch_scopes.values_list("branch_id", flat=True)),
        "inventoryLocationMode": membership.inventory_location_scope_mode,
        "inventoryLocationIds": sorted(
            str(value) for value in membership.inventory_location_scopes.values_list("inventory_location_id", flat=True)
        ),
    }


def _identity_snapshot(membership: CompanyMembership) -> dict[str, object]:
    user = membership.user
    return {
        "username": user.username,
        "email": user.email,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "accessProfileId": str(membership.access_profile_id),
        "accessProfileKey": membership.access_profile.key,
        "accessActive": membership.is_active,
        "accountActive": user.is_active,
        "mustChangePassword": user.must_change_password,
        "scopes": _scope_snapshot(membership),
    }


@transaction.atomic
def create_managed_user(*, actor_membership: CompanyMembership, payload: dict[str, object], request=None) -> CompanyMembership:
    _require_manage_users(actor_membership)
    values = _clean_identity(
        username=payload.get("username"), email=payload.get("email"),
        first_name=payload.get("firstName"), last_name=payload.get("lastName"),
    )
    _validate_identity_uniqueness(values)
    password = str(payload.get("temporaryPassword") or "")
    if not password:
        raise ValidationError({"temporaryPassword": "Temporary password is required."})
    profile = _profile_for_assignment(
        company=actor_membership.company, profile_id=payload.get("accessProfileId"), actor=actor_membership
    )
    scope_assignment = parse_scope_assignment(payload.get("scopes") if isinstance(payload.get("scopes"), dict) else None)

    candidate = User(**values, is_active=True, must_change_password=True, credentials_updated_at=timezone.now())
    password_validation.validate_password(password, user=candidate)
    candidate.full_clean(exclude=("password",))
    candidate.set_password(password)
    candidate.save()
    membership = CompanyMembership.objects.create(
        company=actor_membership.company,
        user=candidate,
        role=_classification_for_profile(profile),
        access_profile=profile,
        is_active=True,
    )
    _apply_scope_assignment(membership=membership, assignment=scope_assignment)
    record_audit_event(
        company=actor_membership.company,
        area=AuditArea.ACCESS,
        action="access.user.created",
        object_type="accounts.CompanyMembership",
        object_id=membership.pk,
        object_label=candidate.display_name,
        actor_membership=actor_membership,
        after=_identity_snapshot(membership),
        metadata={"temporary_password": "set", "sessions_invalidated_by_password_hash": True},
        request=request,
    )
    return membership


@transaction.atomic
def update_managed_user(*, actor_membership: CompanyMembership, membership_id, payload: dict[str, object], request=None) -> CompanyMembership:
    _require_manage_users(actor_membership)
    target = (
        CompanyMembership.objects.select_for_update()
        .select_related("company", "user", "access_profile")
        .get(pk=membership_id, company=actor_membership.company)
    )
    before = _identity_snapshot(target)
    target_is_self = target.pk == actor_membership.pk
    access_fields = {"accessProfileId", "scopes"}
    if target_is_self and any(field in payload for field in access_fields):
        raise PermissionDenied("You cannot change your own access profile or scopes.")
    if _is_owner_profile(target.access_profile) and not _actor_is_owner(actor_membership):
        raise PermissionDenied("Only a Company Owner can modify another Company Owner account.")

    user = target.user
    values = _clean_identity(
        username=payload.get("username", user.username),
        email=payload.get("email", user.email),
        first_name=payload.get("firstName", user.first_name),
        last_name=payload.get("lastName", user.last_name),
    )
    _validate_identity_uniqueness(values, exclude_user_id=user.pk)
    for field, value in values.items():
        setattr(user, field, value)
    user.full_clean(exclude=("password",))
    user.save(update_fields=("username", "email", "first_name", "last_name", "is_staff"))

    if "accessProfileId" in payload:
        profile = _profile_for_assignment(
            company=target.company, profile_id=payload.get("accessProfileId"), actor=actor_membership
        )
        if _is_owner_profile(target.access_profile) and not _is_owner_profile(profile):
            # CompanyMembership.clean performs the locked final-owner check; keep this explicit for clear API intent.
            pass
        target.access_profile = profile
        target.role = _classification_for_profile(profile)
        target.save(update_fields=("access_profile", "role", "updated_at"))
    if "scopes" in payload:
        raw_scopes = payload.get("scopes")
        if not isinstance(raw_scopes, dict):
            raise ValidationError({"scopes": "Scopes must be a JSON object."})
        _apply_scope_assignment(membership=target, assignment=parse_scope_assignment(raw_scopes))

    if "accessProfileId" in payload or "scopes" in payload:
        bump_user_security_version(target.user_id)

    target.refresh_from_db()
    record_audit_event(
        company=target.company,
        area=AuditArea.ACCESS,
        action="access.user.updated",
        object_type="accounts.CompanyMembership",
        object_id=target.pk,
        object_label=target.user.display_name,
        actor_membership=actor_membership,
        before=before,
        after=_identity_snapshot(target),
        request=request,
    )
    return target


@transaction.atomic
def set_managed_user_active(*, actor_membership: CompanyMembership, membership_id, is_active: bool, request=None) -> CompanyMembership:
    _require_manage_users(actor_membership)
    target = (
        CompanyMembership.objects.select_for_update().select_related("company", "user", "access_profile")
        .get(pk=membership_id, company=actor_membership.company)
    )
    if target.pk == actor_membership.pk:
        raise PermissionDenied("You cannot deactivate or reactivate your own access from User Management.")
    if _is_owner_profile(target.access_profile) and not _actor_is_owner(actor_membership):
        raise PermissionDenied("Only a Company Owner can change another Company Owner account status.")
    before = _identity_snapshot(target)
    if is_active and not target.access_profile.is_active:
        raise ValidationError("Assign an active Access Profile before reactivating this user.")
    if is_active:
        if not target.user.is_active:
            target.user.is_active = True
            target.user.save(update_fields=("is_active", "is_staff"))
        target.is_active = True
        target.save(update_fields=("is_active", "updated_at"))
    else:
        target.is_active = False
        target.save(update_fields=("is_active", "updated_at"))
        other_access = CompanyMembership.objects.filter(user=target.user, is_active=True, company__is_active=True).exists()
        if not other_access and target.user.is_active:
            target.user.is_active = False
            target.user.save(update_fields=("is_active", "is_staff"))
    bump_user_security_version(target.user_id)
    target.refresh_from_db()
    record_audit_event(
        company=target.company, area=AuditArea.ACCESS,
        action="access.user.activated" if is_active else "access.user.deactivated",
        object_type="accounts.CompanyMembership", object_id=target.pk,
        object_label=target.user.display_name, actor_membership=actor_membership,
        before=before, after=_identity_snapshot(target), request=request,
    )
    return target


@transaction.atomic
def reset_managed_user_password(*, actor_membership: CompanyMembership, membership_id, temporary_password: str, request=None) -> CompanyMembership:
    _require_manage_users(actor_membership)
    target = (
        CompanyMembership.objects.select_for_update().select_related("company", "user", "access_profile")
        .get(pk=membership_id, company=actor_membership.company)
    )
    if target.pk == actor_membership.pk:
        raise PermissionDenied("Use the personal password-change flow for your own account.")
    if _is_owner_profile(target.access_profile) and not _actor_is_owner(actor_membership):
        raise PermissionDenied("Only a Company Owner can reset another Company Owner password.")
    password = str(temporary_password or "")
    if not password:
        raise ValidationError({"temporaryPassword": "Temporary password is required."})
    password_validation.validate_password(password, user=target.user)
    target.user.set_password(password)
    target.user.must_change_password = True
    target.user.credentials_updated_at = timezone.now()
    target.user.save(update_fields=("password", "must_change_password", "credentials_updated_at", "is_staff"))
    bump_user_security_version(target.user_id)
    record_audit_event(
        company=target.company, area=AuditArea.ACCESS, action="access.user.password_reset",
        object_type="accounts.CompanyMembership", object_id=target.pk, object_label=target.user.display_name,
        actor_membership=actor_membership,
        after={"mustChangePassword": True, "credentialsUpdatedAt": target.user.credentials_updated_at.isoformat()},
        metadata={"temporary_password": "reset", "sessions_invalidated_by_password_hash": True}, request=request,
    )
    return target


@transaction.atomic
def restore_managed_user_access(
    *,
    actor_membership: CompanyMembership,
    membership_id,
    event_id,
    confirmation: str,
    request=None,
) -> CompanyMembership:
    """Reapply the *before* access snapshot from one immutable user audit event.

    Recovery deliberately restores only access authority/state recorded by User
    Management: profile, operational scopes and active flags. Identity fields and
    credentials are never rolled back from audit JSON. Every recovery invalidates
    the target's existing sessions and creates a new immutable audit event.
    """
    _require_manage_users(actor_membership)
    if not membership_has_permission(actor_membership, AccessPermission.ACCESS_AUDIT_VIEW):
        raise PermissionDenied("Your access profile cannot use Access History recovery.")

    target = (
        CompanyMembership.objects.select_for_update()
        .select_related("company", "user", "access_profile")
        .get(pk=membership_id, company=actor_membership.company)
    )
    if target.pk == actor_membership.pk:
        raise PermissionDenied("You cannot restore your own historical access configuration.")
    if _is_owner_profile(target.access_profile) and not _actor_is_owner(actor_membership):
        raise PermissionDenied("Only a Company Owner can recover another Company Owner account.")
    if str(confirmation or "").strip() != target.user.username:
        raise ValidationError({"confirmation": "Type the exact username to confirm access recovery."})

    try:
        source_event = AuditEvent.objects.get(
            pk=event_id,
            company=target.company,
            area=AuditArea.ACCESS,
            object_type="accounts.CompanyMembership",
            object_id=str(target.pk),
        )
    except (AuditEvent.DoesNotExist, ValueError) as exc:
        raise ValidationError({"eventId": "Choose a valid Access History event for this user."}) from exc

    allowed_actions = {
        "access.user.updated",
        "access.user.activated",
        "access.user.deactivated",
        "access.user.access_restored",
    }
    snapshot = source_event.before if isinstance(source_event.before, dict) else {}
    if source_event.action not in allowed_actions or not snapshot.get("accessProfileId") or not isinstance(snapshot.get("scopes"), dict):
        raise ValidationError({"eventId": "This audit event does not contain a recoverable prior access snapshot."})
    if not isinstance(snapshot.get("accessActive"), bool):
        raise ValidationError({"eventId": "This historical snapshot does not contain a valid access state."})

    profile = _profile_for_assignment(
        company=target.company, profile_id=snapshot.get("accessProfileId"), actor=actor_membership
    )
    assignment = parse_scope_assignment(snapshot.get("scopes"))
    restore_access_active = bool(snapshot["accessActive"])
    restore_account_active = snapshot.get("accountActive")
    if not isinstance(restore_account_active, bool):
        restore_account_active = target.user.is_active
    if restore_access_active and not profile.is_active:
        raise ValidationError("The historical Access Profile is inactive. Reactivate or replace it before recovery.")

    before = _identity_snapshot(target)
    target.access_profile = profile
    target.role = _classification_for_profile(profile)
    target.is_active = restore_access_active
    target.save(update_fields=("access_profile", "role", "is_active", "updated_at"))
    _apply_scope_assignment(membership=target, assignment=assignment)

    if target.user.is_active != restore_account_active:
        target.user.is_active = restore_account_active
        target.user.save(update_fields=("is_active", "is_staff"))

    bump_user_security_version(target.user_id)
    target.refresh_from_db()
    after = _identity_snapshot(target)
    record_audit_event(
        company=target.company,
        area=AuditArea.ACCESS,
        action="access.user.access_restored",
        object_type="accounts.CompanyMembership",
        object_id=target.pk,
        object_label=target.user.display_name,
        actor_membership=actor_membership,
        before=before,
        after=after,
        metadata={
            "sourceEventId": str(source_event.pk),
            "sourceAction": source_event.action,
            "snapshotSide": "before",
            "sessionsInvalidated": True,
        },
        request=request,
    )
    return target


@transaction.atomic
def delete_unused_managed_user(*, actor_membership: CompanyMembership, membership_id, confirmation: str, request=None) -> None:
    _require_manage_users(actor_membership)
    target = (
        CompanyMembership.objects.select_for_update().select_related("company", "user", "access_profile")
        .get(pk=membership_id, company=actor_membership.company)
    )
    if target.pk == actor_membership.pk:
        raise PermissionDenied("You cannot delete your own account.")
    if _is_owner_profile(target.access_profile):
        raise ValidationError("Owner accounts cannot be hard-deleted; deactivate a non-final owner instead.")
    user = target.user
    if str(confirmation or "").strip() != user.username:
        raise ValidationError({"confirmation": "Type the exact username to confirm deletion."})
    if user.last_login is not None or AuditEvent.objects.filter(actor=user).exists():
        raise ValidationError("This account has activity history and must be deactivated instead of deleted.")
    if CompanyMembership.objects.filter(user=user).exclude(pk=target.pk).exists():
        raise ValidationError("This identity belongs to another company and cannot be deleted here.")
    reference_blockers: list[str] = []
    for relation in user._meta.related_objects:
        if relation.related_model is CompanyMembership:
            continue
        accessor = relation.get_accessor_name()
        if not accessor:
            continue
        try:
            related = getattr(user, accessor, None)
            exists = related.exists() if hasattr(related, "exists") else related is not None
        except ObjectDoesNotExist:
            exists = False
        except Exception:
            exists = True
        if exists:
            reference_blockers.append(relation.related_model._meta.label)
    if reference_blockers:
        raise ValidationError(
            "This account is already referenced by system history and must be deactivated instead of deleted."
        )
    snapshot = _identity_snapshot(target)
    record_audit_event(
        company=target.company, area=AuditArea.ACCESS, action="access.user.deleted_unused",
        object_type="accounts.CompanyMembership", object_id=target.pk, object_label=user.display_name,
        actor_membership=actor_membership, before=snapshot,
        metadata={"guard": "never-signed-in/no-actor-history/no-domain-references/single-membership"}, request=request,
    )
    user.delete()


def user_membership_page(*, company, query: str = "", status: str = "all", page=1, page_size=25) -> dict[str, object]:
    try:
        page = max(1, int(page))
        page_size = int(page_size)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"page": "Page and page size must be integers."}) from exc
    if page_size not in USER_PAGE_SIZES:
        raise ValidationError({"pageSize": "Page size must be 25, 50, or 100."})
    q = str(query or "").strip()
    if q and len(q) < 2:
        raise ValidationError({"q": "Enter at least 2 characters to search users."})
    qs = (
        CompanyMembership.objects.filter(company=company)
        .select_related("user", "access_profile")
        .prefetch_related("project_scopes", "branch_scopes", "inventory_location_scopes")
        .order_by("user__first_name", "user__last_name", "user__username", "id")
    )
    if q:
        qs = qs.filter(
            Q(user__username__icontains=q) | Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q) |
            Q(access_profile__name__icontains=q)
        )
    normalized_status = str(status or "all").strip().lower()
    if normalized_status == "active":
        qs = qs.filter(is_active=True, user__is_active=True, access_profile__is_active=True)
    elif normalized_status == "inactive":
        qs = qs.filter(Q(is_active=False) | Q(user__is_active=False) | Q(access_profile__is_active=False))
    elif normalized_status != "all":
        raise ValidationError({"status": "Status must be active, inactive, or all."})
    offset = (page - 1) * page_size
    rows = list(qs[offset: offset + page_size + 1])
    has_next = len(rows) > page_size
    rows = rows[:page_size]
    return {
        "rows": [serialize_user_membership(row, detail=False) for row in rows],
        "page": page,
        "pageSize": page_size,
        "hasNext": has_next,
        "hasPrevious": page > 1,
        "query": q,
        "status": normalized_status,
    }


def serialize_user_membership(membership: CompanyMembership, *, detail: bool) -> dict[str, object]:
    user = membership.user
    payload: dict[str, object] = {
        "membershipId": str(membership.pk),
        "userId": str(user.pk),
        "username": user.username,
        "firstName": user.first_name,
        "lastName": user.last_name,
        "displayName": user.display_name,
        "email": user.email,
        "active": bool(user.is_active and membership.is_active and membership.access_profile.is_active),
        "accountActive": user.is_active,
        "accessActive": membership.is_active,
        "mustChangePassword": user.must_change_password,
        "lastLogin": user.last_login.isoformat() if user.last_login else None,
        "joinedAt": membership.joined_at.isoformat() if membership.joined_at else None,
        "updatedAt": membership.updated_at.isoformat(),
        "profile": {
            "id": str(membership.access_profile_id),
            "key": membership.access_profile.key,
            "name": membership.access_profile.name,
            "system": membership.access_profile.is_system,
            "active": membership.access_profile.is_active,
            "owner": _is_owner_profile(membership.access_profile),
        },
        "scopes": {
            "projects": {"mode": membership.project_scope_mode, "count": membership.project_scopes.count()},
            "branches": {"mode": membership.branch_scope_mode, "count": membership.branch_scopes.count()},
            "inventoryLocations": {"mode": membership.inventory_location_scope_mode, "count": membership.inventory_location_scopes.count()},
        },
    }
    if detail:
        payload["scopes"] = {
            "projects": {"mode": membership.project_scope_mode, "rows": [
                {"id": str(item.project_id), "code": item.project.code, "name": item.project.name}
                for item in membership.project_scopes.select_related("project").order_by("project__code")
            ]},
            "branches": {"mode": membership.branch_scope_mode, "rows": [
                {"id": str(item.branch_id), "code": item.branch.code, "name": item.branch.name, "kind": item.branch.kind}
                for item in membership.branch_scopes.select_related("branch").order_by("branch__code")
            ]},
            "inventoryLocations": {"mode": membership.inventory_location_scope_mode, "rows": [
                {"id": str(item.inventory_location_id), "code": item.inventory_location.code, "name": item.inventory_location.name, "type": item.inventory_location.location_type}
                for item in membership.inventory_location_scopes.select_related("inventory_location").order_by("inventory_location__code")
            ]},
        }
    return payload


def managed_user_detail(*, company, membership_id) -> CompanyMembership:
    return (
        CompanyMembership.objects.filter(company=company, pk=membership_id)
        .select_related("user", "access_profile")
        .get()
    )
