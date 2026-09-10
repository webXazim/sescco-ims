from __future__ import annotations

from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace


class ActiveCompanyAdminMixin:
    """Scope a Django-admin model to the request's active company.

    Set ``company_lookup`` for child records whose tenant is reached through a parent relation,
    for example ``job__company``. The admin remains unavailable when the request has no active
    Inventory workspace membership.
    """

    company_lookup = "company"
    workspace = Workspace.INVENTORY

    def _membership(self, request):
        return getattr(request, "company_membership", None)

    def has_module_permission(self, request):
        return membership_can_workspace(self._membership(request), self.workspace)

    def has_view_permission(self, request, obj=None):
        if not membership_can_workspace(self._membership(request), self.workspace):
            return False
        if obj is None:
            return True
        company = getattr(request, "company", None)
        if company is None:
            return False
        current = obj
        parts = self.company_lookup.split("__")
        for part in parts:
            current = getattr(current, part, None)
            if current is None:
                return False
        return getattr(current, "pk", current) == company.pk

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        company = getattr(request, "company", None)
        if company is None:
            return queryset.none()
        return queryset.filter(**{self.company_lookup: company})
