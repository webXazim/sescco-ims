from __future__ import annotations

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event

from .models import CompanyMembership, User
from .permissions import membership_has_capability
from .roles import AccessRole, Capability
from .selectors import ACTIVE_COMPANY_SESSION_KEY, active_memberships_for_user


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
    if role not in AccessRole.values:
        raise ValidationError({"role": "Unknown company role."})

    membership, created = CompanyMembership.objects.get_or_create(
        company=actor_membership.company,
        user=user,
        defaults={"role": role, "is_active": True},
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
        after={"user_id": str(user.pk), "role": role, "is_active": True},
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
    if role not in AccessRole.values:
        raise ValidationError({"role": "Unknown company role."})

    target = (
        CompanyMembership.objects.select_for_update()
        .select_related("company", "user")
        .get(id=membership_id, company=actor_membership.company)
    )
    previous_role = target.role
    if previous_role == role:
        return target

    if target.role == AccessRole.OWNER and role != AccessRole.OWNER:
        active_owner_count = (
            CompanyMembership.objects.select_for_update()
            .filter(company=target.company, role=AccessRole.OWNER, is_active=True, user__is_active=True)
            .count()
        )
        if target.is_active and target.user.is_active and active_owner_count <= 1:
            raise ValidationError("A company must keep at least one active owner.")

    target.role = role
    target.save(update_fields=("role", "updated_at"))
    record_audit_event(
        company=target.company,
        area=AuditArea.ACCESS,
        action="access.membership.role_changed",
        object_type="accounts.CompanyMembership",
        object_id=target.pk,
        object_label=target.user.display_name,
        actor_membership=actor_membership,
        before={"role": previous_role},
        after={"role": target.role},
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
        .select_related("company", "user")
        .get(id=membership_id, company=actor_membership.company)
    )
    previous_active = target.is_active
    if previous_active == is_active:
        return target

    if target.role == AccessRole.OWNER and target.is_active and not is_active and target.user.is_active:
        active_owner_count = (
            CompanyMembership.objects.select_for_update()
            .filter(company=target.company, role=AccessRole.OWNER, is_active=True, user__is_active=True)
            .count()
        )
        if active_owner_count <= 1:
            raise ValidationError("A company must keep at least one active owner.")

    target.is_active = is_active
    target.save(update_fields=("is_active", "updated_at"))
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
