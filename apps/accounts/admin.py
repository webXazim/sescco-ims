from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class InventoryUserAdmin(UserAdmin):
    list_display = (
        "username",
        "display_name",
        "email",
        "role",
        "is_active",
        "last_login",
    )
    list_filter = ("role", "is_active", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    list_per_page = 50
    readonly_fields = ("is_staff", "last_login", "date_joined")
    fieldsets = (
        ("Account", {"fields": ("username", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "email")}),
        (
            "Inventory access",
            {
                "fields": ("role", "is_active", "is_staff"),
                "description": (
                    "Role controls workspace access. Administrator automatically "
                    "enables Django staff access; deactivate accounts instead of deleting them."
                ),
            },
        ),
        (
            "Advanced Django permissions",
            {
                "fields": ("is_superuser", "groups", "user_permissions"),
                "classes": ("collapse",),
            },
        ),
        ("Sign-in history", {"fields": ("last_login", "date_joined"), "classes": ("collapse",)}),
    )
    add_fieldsets = (
        (
            "Create account",
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2", "role", "is_active"),
            },
        ),
    )
    actions = ("activate_accounts", "deactivate_accounts")

    @admin.action(description="Activate selected accounts")
    def activate_accounts(self, request, queryset):
        count = queryset.update(is_active=True)
        self.message_user(request, f"Activated {count} account(s).")

    @admin.action(description="Deactivate selected accounts")
    def deactivate_accounts(self, request, queryset):
        safe_accounts = queryset.exclude(pk=request.user.pk).exclude(is_superuser=True)
        count = safe_accounts.update(is_active=False)
        self.message_user(
            request,
            f"Deactivated {count} account(s). Your own account and superusers were kept active.",
        )


admin.site.site_header = "Project Inventory Administration"
admin.site.site_title = "Project Inventory Admin"
admin.site.index_title = "System administration"
admin.site.site_url = "/app/"
admin.site.empty_value_display = "—"
