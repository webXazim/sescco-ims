from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class InventoryWorkspaceMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restrict the operational workspace to active inventory users."""

    raise_exception = True

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
