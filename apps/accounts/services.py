from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from .access_catalog import system_profile_key_for_role
from .models import CompanyMembership, User
from .permissions import membership_has_capability
from .roles import AccessRole, Capability
from .selectors import ACTIVE_COMPANY_SESSION_KEY, active_memberships_for_user
from .access_provisioning import ensure_system_access_profile
from .security import bump_user_security_version


@transaction.atomic
def create_company_membership(
    *,
    actor_membership: CompanyMembership,
    user: User,
    role: str,
    request: HttpRequest | None = None,
) -> CompanyMembership:
    if not membership_has_capability(actor_membership, Capability.MANAGE_ACCESS):
        raise PermissionDenied("Only company access administrators can add members.")
    if role not in AccessRole.values or role == AccessRole.CUSTOM:
        raise ValidationError({"role": "Choose a built-in company role; custom access uses an explicit Access Profile."})

    profile = ensure_system_access_profile(company=actor_membership.company, role=role)
    membership, created = CompanyMembership.objects.get_or_create(
        company=actor_membership.company,
        user=user,
        defaults={"role": role, "access_profile": profile, "is_active": True},
    )
    if not created:
        raise ValidationError("This user already belongs to the company.")

    record_audit_event(
        company=actor_membership.company,
        area=AuditArea.ACCESS,
        action="access.membership.created",
        object_type="accounts.CompanyMembership",
        object_id=membership.pk,
        object_label=user.display_name,
        actor_membership=actor_membership,
        after={"user_id": str(user.pk), "role": role, "access_profile": profile.key, "is_active": True},
        request=request,
    )
    return membership


def activate_company(request: HttpRequest, company_id) -> CompanyMembership:
    if settings.SINGLE_COMPANY_MODE:
        raise PermissionDenied("Company switching is disabled in SESCCO MS single-company mode.")
    membership = active_memberships_for_user(request.user).filter(company_id=company_id).first()
    if membership is None:
        raise PermissionDenied("You do not have access to that company.")
    request.session[ACTIVE_COMPANY_SESSION_KEY] = str(membership.company_id)
    request.company = membership.company
    request.company_membership = membership
    return membership


@transaction.atomic
def change_membership_role(
    *,
    actor_membership: CompanyMembership,
    membership_id,
    role: str,
    request: HttpRequest | None = None,
) -> CompanyMembership:
    if not membership_has_capability(actor_membership, Capability.MANAGE_ACCESS):
        raise PermissionDenied("Only company access administrators can change roles.")
    if role not in AccessRole.values or role == AccessRole.CUSTOM:
        raise ValidationError({"role": "Choose a built-in company role; custom access uses an explicit Access Profile."})

    target = (
        CompanyMembership.objects.select_for_update()
        .select_related("company", "user", "access_profile")
        .get(id=membership_id, company=actor_membership.company)
    )
    previous_role = target.role
    if previous_role == role:
        return target

    owner_key = system_profile_key_for_role(AccessRole.OWNER)
    target_is_owner = bool(
        target.access_profile_id
        and target.access_profile.key == owner_key
        and target.access_profile.is_system
        and target.access_profile.is_active
    )
    if target_is_owner and role != AccessRole.OWNER:
        active_owner_count = (
            CompanyMembership.objects.select_for_update()
            .filter(
                company=target.company, access_profile__key=owner_key,
                access_profile__is_system=True, access_profile__is_active=True,
                is_active=True, user__is_active=True,
            )
            .count()
        )
        if target.is_active and target.user.is_active and active_owner_count <= 1:
            raise ValidationError("A company must keep at least one active owner profile.")

    target.role = role
    target.access_profile = ensure_system_access_profile(company=target.company, role=role)
    target.save(update_fields=("role", "access_profile", "updated_at"))
    bump_user_security_version(target.user_id)
    record_audit_event(
        company=target.company,
        area=AuditArea.ACCESS,
        action="access.membership.role_changed",
        object_type="accounts.CompanyMembership",
        object_id=target.pk,
        object_label=target.user.display_name,
        actor_membership=actor_membership,
        before={"role": previous_role},
        after={"role": target.role, "access_profile": target.access_profile.key},
        request=request,
    )
    return target


@transaction.atomic
def set_membership_active(
    *,
    actor_membership: CompanyMembership,
    membership_id,
    is_active: bool,
    request: HttpRequest | None = None,
) -> CompanyMembership:
    if not membership_has_capability(actor_membership, Capability.MANAGE_ACCESS):
        raise PermissionDenied("Only company access administrators can change access.")

    target = (
        CompanyMembership.objects.select_for_update()
        .select_related("company", "user", "access_profile")
        .get(id=membership_id, company=actor_membership.company)
    )
    previous_active = target.is_active
    if previous_active == is_active:
        return target

    owner_key = system_profile_key_for_role(AccessRole.OWNER)
    target_is_owner = bool(
        target.access_profile_id
        and target.access_profile.key == owner_key
        and target.access_profile.is_system
        and target.access_profile.is_active
    )
    if target_is_owner and target.is_active and not is_active and target.user.is_active:
        active_owner_count = (
            CompanyMembership.objects.select_for_update()
            .filter(
                company=target.company, access_profile__key=owner_key,
                access_profile__is_system=True, access_profile__is_active=True,
                is_active=True, user__is_active=True,
            )
            .count()
        )
        if active_owner_count <= 1:
            raise ValidationError("A company must keep at least one active owner profile.")

    target.is_active = is_active
    target.save(update_fields=("is_active", "updated_at"))
    bump_user_security_version(target.user_id)
    record_audit_event(
        company=target.company,
        area=AuditArea.ACCESS,
        action="access.membership.activation_changed",
        object_type="accounts.CompanyMembership",
        object_id=target.pk,
        object_label=target.user.display_name,
        actor_membership=actor_membership,
        before={"is_active": previous_active},
        after={"is_active": target.is_active},
        request=request,
    )
    return target
