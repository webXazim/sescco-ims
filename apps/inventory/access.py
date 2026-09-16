from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db.models import Q, QuerySet

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import (
    membership_allows_inventory_location,
    membership_allows_project,
    membership_has_permission,
    restrict_inventory_locations,
    restrict_projects,
)
from apps.accounts.models import CompanyMembership


def require_inventory_permission(
    membership: CompanyMembership | None,
    permission: AccessPermission | str,
    *,
    message: str = "Your access profile does not allow this Inventory action.",
) -> CompanyMembership:
    if membership is None or not membership_has_permission(membership, permission):
        raise PermissionDenied(message)
    return membership


def location_in_inventory_scope(membership: CompanyMembership | None, location) -> bool:
    """Inventory location scope plus Project scope for project-backed locations.

    Office locations are governed by Inventory Location scope only. Project locations
    must pass both the Inventory Location and Project scopes. This prevents a selected
    project grant from being bypassed through its auto-created InventoryLocation row.
    """

    if membership is None or location is None:
        return False
    if not membership_allows_inventory_location(membership, location):
        return False
    project = getattr(location, "project", None)
    if project is None and getattr(location, "project_id", None):
        project = location.project
    if project is not None and not membership_allows_project(membership, project):
        return False
    return True


def project_in_inventory_scope(membership: CompanyMembership | None, project) -> bool:
    if membership is None or project is None or not membership_allows_project(membership, project):
        return False
    try:
        location = project.inventory_location
    except Exception:  # RelatedObjectDoesNotExist without importing the model here.
        return False
    return membership_allows_inventory_location(membership, location)


def restrict_inventory_projects(queryset: QuerySet, membership: CompanyMembership | None) -> QuerySet:
    queryset = restrict_projects(queryset, membership)
    if membership is None:
        return queryset.none()
    mode = membership.inventory_location_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.none()
    location_project_ids = membership.inventory_location_scopes.filter(
        inventory_location__project_id__isnull=False
    ).values_list("inventory_location__project_id", flat=True)
    return queryset.filter(pk__in=location_project_ids)


def restrict_inventory_location_queryset(
    queryset: QuerySet,
    membership: CompanyMembership | None,
    *,
    field: str = "pk",
    project_field: str = "project_id",
) -> QuerySet:
    queryset = restrict_inventory_locations(queryset, membership, field=field)
    if membership is None:
        return queryset.none()
    project_mode = membership.project_scope_mode
    if project_mode == "all":
        return queryset
    if project_mode == "none":
        return queryset.filter(**{f"{project_field}__isnull": True})
    project_ids = membership.project_scopes.values_list("project_id", flat=True)
    return queryset.filter(
        Q(**{f"{project_field}__isnull": True})
        | Q(**{f"{project_field}__in": project_ids})
    )


def restrict_inventory_stock(queryset: QuerySet, membership: CompanyMembership | None) -> QuerySet:
    queryset = restrict_inventory_locations(queryset, membership, field="location_id")
    if membership is None:
        return queryset.none()
    mode = membership.project_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.filter(project_id__isnull=True)
    project_ids = membership.project_scopes.values_list("project_id", flat=True)
    return queryset.filter(Q(project_id__isnull=True) | Q(project_id__in=project_ids))


def restrict_inventory_movements(queryset: QuerySet, membership: CompanyMembership | None) -> QuerySet:
    queryset = restrict_inventory_locations(queryset, membership, field="stock_item__location_id")
    if membership is None:
        return queryset.none()
    mode = membership.project_scope_mode
    if mode == "all":
        return queryset
    if mode == "none":
        return queryset.filter(stock_item__project_id__isnull=True)
    project_ids = membership.project_scopes.values_list("project_id", flat=True)
    return queryset.filter(
        Q(stock_item__project_id__isnull=True) | Q(stock_item__project_id__in=project_ids)
    )


def restrict_inventory_transfers(queryset: QuerySet, membership: CompanyMembership | None) -> QuerySet:
    """Transfers are visible only when both ends are inside the actor's scope."""

    if membership is None:
        return queryset.none()
    source_ids = restrict_inventory_location_queryset(
        queryset.model._meta.get_field("source_location").related_model.objects.for_company(membership.company),
        membership,
    ).values_list("pk", flat=True)
    destination_ids = restrict_inventory_location_queryset(
        queryset.model._meta.get_field("destination_location").related_model.objects.for_company(membership.company),
        membership,
    ).values_list("pk", flat=True)
    return queryset.filter(source_location_id__in=source_ids, destination_location_id__in=destination_ids)
