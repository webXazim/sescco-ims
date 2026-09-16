from __future__ import annotations

from django.conf import settings
from django.db.models import QuerySet

from .access_catalog import system_profile_key_for_role
from .models import AccessProfile, CompanyMembership, User


ACTIVE_COMPANY_SESSION_KEY = "active_company_id"


def active_memberships_for_user(user: User) -> QuerySet[CompanyMembership]:
    return (
        CompanyMembership.objects.select_related("company", "company__settings", "user", "access_profile")
        .prefetch_related("access_profile__permission_grants")
        .filter(user=user, is_active=True, company__is_active=True)
        .order_by("company__name", "created_at")
    )


def resolve_membership(user: User, company_id: str | None = None) -> CompanyMembership | None:
    memberships = active_memberships_for_user(user)
    if settings.SINGLE_COMPANY_MODE:
        primary_slug = settings.PRIMARY_COMPANY_SLUG
        if primary_slug:
            memberships = memberships.filter(company__slug=primary_slug)
        # In single-company mode the session can never steer the request into a
        # different tenant. Production checks guarantee that this is unambiguous.
        return memberships.first()
    if company_id:
        membership = memberships.filter(company_id=company_id).first()
        if membership is not None:
            return membership
    return memberships.first()


def system_access_profile_for_role(company, role: str) -> AccessProfile | None:
    return (
        AccessProfile.objects.filter(
            company=company,
            key=system_profile_key_for_role(role),
            is_system=True,
            is_active=True,
        )
        .first()
    )
