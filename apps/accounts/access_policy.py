from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db.models import QuerySet

from .access_catalog import AccessPermission

if TYPE_CHECKING:
    from .models import CompanyMembership


@dataclass(frozen=True, slots=True)
class EffectiveAccess:
    membership_id: str
    company_id: str
    profile_id: str | None
    profile_key: str
    profile_name: str
    profile_is_system: bool
    permissions: frozenset[str]
    project_scope_mode: str
    branch_scope_mode: str
    inventory_location_scope_mode: str

    def has(self, permission: AccessPermission | str) -> bool:
        value = permission.value if isinstance(permission, AccessPermission) else str(permission)
        return value in self.permissions

    def as_frontend_dict(self) -> dict[str, object]:
        return {
            "profile": {
                "id": self.profile_id,
                "key": self.profile_key,
                "name": self.profile_name,
                "system": self.profile_is_system,
            },
            "permissions": sorted(self.permissions),
            "scopes": {
                "projects": self.project_scope_mode,
                "branches": self.branch_scope_mode,
                "inventory_locations": self.inventory_location_scope_mode,
            },
        }


def _membership_is_usable(membership: CompanyMembership | None) -> bool:
    return bool(
        membership is not None
        and membership.is_active
        and membership.user.is_active
        and membership.company.is_active
    )


def effective_access_for_membership(membership: CompanyMembership | None) -> EffectiveAccess | None:
    if not _membership_is_usable(membership):
        return None

    cached = getattr(membership, "_effective_access_cache", None)
    if cached is not None:
        return cached

    profile = getattr(membership, "access_profile", None)
    if profile is not None and profile.is_active:
        values = frozenset(grant.permission for grant in profile.permission_grants.all())
        profile_id = str(profile.id)
        profile_key = profile.key
        profile_name = profile.name
        profile_is_system = profile.is_system
    elif profile is not None:
        # Assigned-but-inactive profiles always fail closed.
        values = frozenset()
        profile_id = str(profile.id)
        profile_key = profile.key
        profile_name = profile.name
        profile_is_system = profile.is_system
    else:
        # 1.0.89 retires the legacy role fallback completely. A missing profile is a
        # reconciliation error and receives no application permissions.
        values = frozenset()
        profile_id = None
        profile_key = "missing-profile"
        profile_name = "No access profile"
        profile_is_system = False

    access = EffectiveAccess(
        membership_id=str(membership.id),
        company_id=str(membership.company_id),
        profile_id=profile_id,
        profile_key=profile_key,
        profile_name=profile_name,
        profile_is_system=profile_is_system,
        permissions=values,
        project_scope_mode=membership.project_scope_mode,
        branch_scope_mode=membership.branch_scope_mode,
        inventory_location_scope_mode=membership.inventory_location_scope_mode,
    )
    membership._effective_access_cache = access
    return access


def membership_has_permission(
    membership: CompanyMembership | None,
    permission: AccessPermission | str,
) -> bool:
    access = effective_access_for_membership(membership)
    return bool(access and access.has(permission))


def _scope_mode_allows(*, mode: str, exists: bool) -> bool:
    if mode == "all":
        return True
    if mode == "none":
        return False
    return exists


def membership_allows_project(membership: CompanyMembership | None, project) -> bool:
    if not _membership_is_usable(membership) or project is None:
        return False
    if getattr(project, "company_id", None) != membership.company_id:
        return False
    mode = membership.project_scope_mode
    if mode == "all":
        return True
    if mode == "none":
        return False
    return membership.project_scopes.filter(project_id=project.pk).exists()


def membership_allows_branch(membership: CompanyMembership | None, branch) -> bool:
    if not _membership_is_usable(membership) or branch is None:
        return False
    if getattr(branch, "company_id", None) != membership.company_id:
        return False
    mode = membership.branch_scope_mode
    if mode == "all":
        return True
    if mode == "none":
        return False
    return membership.branch_scopes.filter(branch_id=branch.pk).exists()


def membership_allows_inventory_location(membership: CompanyMembership | None, location) -> bool:
    if not _membership_is_usable(membership) or location is None:
        return False
    if getattr(location, "company_id", None) != membership.company_id:
        return False
    mode = membership.inventory_location_scope_mode
    if mode == "all":
        return True
    if mode == "none":
        return False
    return membership.inventory_location_scopes.filter(inventory_location_id=location.pk).exists()


def restrict_projects(queryset: QuerySet, membership: CompanyMembership | None, *, field: str = "pk") -> QuerySet:
    if not _membership_is_usable(membership):
        return queryset.none()
    mode = membership.project_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.none()
    ids = membership.project_scopes.values_list("project_id", flat=True)
    return queryset.filter(**{f"{field}__in": ids})


def restrict_branches(queryset: QuerySet, membership: CompanyMembership | None, *, field: str = "pk") -> QuerySet:
    if not _membership_is_usable(membership):
        return queryset.none()
    mode = membership.branch_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.none()
    ids = membership.branch_scopes.values_list("branch_id", flat=True)
    return queryset.filter(**{f"{field}__in": ids})



def branch_scope_ids(membership: CompanyMembership | None):
    """Return the selected Branch/Office ids or ``None`` for company-wide access.

    An empty tuple is fail-closed and represents an explicit ``none`` scope.
    """
    if not _membership_is_usable(membership):
        return ()
    if membership.branch_scope_mode == "all":
        return None
    if membership.branch_scope_mode == "none":
        return ()
    return tuple(membership.branch_scopes.values_list("branch_id", flat=True))


def project_scope_ids(membership: CompanyMembership | None):
    """Return selected Project ids or ``None`` for company-wide access."""
    if not _membership_is_usable(membership):
        return ()
    if membership.project_scope_mode == "all":
        return None
    if membership.project_scope_mode == "none":
        return ()
    return tuple(membership.project_scopes.values_list("project_id", flat=True))


def restrict_branch_snapshots(
    queryset: QuerySet, membership: CompanyMembership | None, *, field: str = "branch_id_snapshot"
) -> QuerySet:
    """Restrict immutable/internal snapshot rows by the Branch id stored on the snapshot."""
    ids = branch_scope_ids(membership)
    if ids is None:
        return queryset
    if not ids:
        return queryset.none()
    return queryset.filter(**{f"{field}__in": ids})


def restrict_current_employee_branches(
    queryset: QuerySet, membership: CompanyMembership | None, *, employee_field: str = "pk"
) -> QuerySet:
    """Restrict live employee-backed rows to the employee's current Branch/Office.

    Historical payroll/payment surfaces should prefer :func:`restrict_branch_snapshots` so
    an employee transfer does not rewrite historical access semantics.
    """
    ids = branch_scope_ids(membership)
    if ids is None:
        return queryset
    if not ids:
        return queryset.none()
    prefix = f"{employee_field}__" if employee_field else ""
    return queryset.filter(
        **{
            f"{prefix}organization_assignments__effective_to__isnull": True,
            f"{prefix}organization_assignments__branch_id__in": ids,
        }
    ).distinct()

def restrict_inventory_locations(
    queryset: QuerySet,
    membership: CompanyMembership | None,
    *,
    field: str = "pk",
) -> QuerySet:
    if not _membership_is_usable(membership):
        return queryset.none()
    mode = membership.inventory_location_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.none()
    ids = membership.inventory_location_scopes.values_list("inventory_location_id", flat=True)
    return queryset.filter(**{f"{field}__in": ids})


def membership_has_company_wide_scopes(membership: CompanyMembership | None) -> bool:
    """Return True only when all governed data dimensions are company-wide.

    Cross-domain aggregate/audit surfaces cannot be safely redacted by a single dimension,
    so narrowed memberships fail closed instead of leaking counts or identifiers.
    """
    return bool(
        _membership_is_usable(membership)
        and membership.branch_scope_mode == "all"
        and membership.project_scope_mode == "all"
        and membership.inventory_location_scope_mode == "all"
    )
