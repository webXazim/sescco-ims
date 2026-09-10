from __future__ import annotations

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company


def primary_company() -> Company:
    """Return the deterministic company created by the merge access migration.

    Test databases created from migrations already contain exactly one company. The fallback
    creation keeps isolated model tests usable when a runner bypasses data migrations.
    """

    company = Company.objects.order_by("created_at", "id").first()
    if company is not None:
        return company
    return Company.objects.create(name="Test Company", legal_name="Test Company", slug="test-company")


def grant_company_access(
    user: User,
    *,
    company: Company | None = None,
    role: str | None = None,
) -> CompanyMembership:
    company = company or primary_company()
    if role is None:
        if user.is_superuser:
            role = AccessRole.OWNER
        elif user.role == User.Role.ADMIN:
            role = AccessRole.OPERATIONS_ADMIN
        else:
            role = AccessRole.STOREKEEPER
    membership, _ = CompanyMembership.objects.update_or_create(
        company=company,
        user=user,
        defaults={"role": role, "is_active": True},
    )
    return membership
