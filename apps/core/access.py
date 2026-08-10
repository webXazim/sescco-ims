from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import redirect_to_login


class InventoryWorkspaceMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict the operational workspace to active inventory users."""

    raise_exception = True

    def handle_no_permission(self):
        # Anonymous visitors should follow the normal sign-in flow. Authenticated
        # users who fail the workspace permission check still receive a hard 403.
        if not self.request.user.is_authenticated:
            return redirect_to_login(
                self.request.get_full_path(),
                self.get_login_url(),
                self.get_redirect_field_name(),
            )
        return super().handle_no_permission()

    def test_func(self) -> bool:
        user = self.request.user
        return bool(user.is_authenticated and user.is_active)


class InventoryAdminRequiredMixin(InventoryWorkspaceMixin):
    """Restrict sensitive corrective operations to inventory administrators."""

    def test_func(self) -> bool:
        user = self.request.user
        return bool(
            super().test_func()
            and getattr(user, "is_inventory_admin", False)
        )
