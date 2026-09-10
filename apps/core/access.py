from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login

from apps.accounts.permissions import membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace


class InventoryWorkspaceMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Require active company-scoped Inventory workspace access."""

    raise_exception = True

    def handle_no_permission(self):
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()

    def test_func(self) -> bool:
        return membership_can_workspace(
            getattr(self.request, "company_membership", None), Workspace.INVENTORY
        )


class InventoryAdminRequiredMixin(InventoryWorkspaceMixin):
    """Require company-scoped Inventory management authority."""

    def test_func(self) -> bool:
        return bool(
            super().test_func()
            and membership_has_capability(
                getattr(self.request, "company_membership", None),
                Capability.MANAGE_INVENTORY,
            )
        )
