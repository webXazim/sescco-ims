from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError

from .models import CompanyMembership, User


class CompanyMembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    fields = ("company", "role", "is_active", "joined_at")
    readonly_fields = ("joined_at",)
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)


@admin.register(User)
class InventoryUserAdmin(UserAdmin):
    inlines = (CompanyMembershipInline,)
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
            "Legacy Inventory compatibility",
            {
                "fields": ("role", "is_active", "is_staff"),
                "description": (
                    "The legacy Inventory role remains during the staged merge. CompanyMembership "
                    "is the new company-scoped authority and becomes authoritative for Inventory "
                    "in Upgrade 4."
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
        count = 0
        protected = 0
        for account in queryset.exclude(pk=request.user.pk).exclude(is_superuser=True):
            if not account.is_active:
                continue
            account.is_active = False
            try:
                account.save(update_fields=("is_active", "is_staff", "role"))
            except ValidationError:
                protected += 1
                continue
            count += 1
        self.message_user(
            request,
            f"Deactivated {count} account(s); kept {protected} sole-owner account(s) active. "
            "Your own account and superusers were also protected.",
        )

    def has_delete_permission(self, request, obj=None):
        # Deactivate identities instead of deleting them so company membership and audit history remain intact.
        return False


@admin.register(CompanyMembership)
class CompanyMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "company", "role", "is_active", "joined_at")
    list_filter = ("role", "is_active", "company")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "company__name")
    ordering = ("company__name", "user__username")
    readonly_fields = ("id", "joined_at", "created_at", "updated_at")
    list_select_related = ("user", "company")

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        # Access is deactivated rather than deleted so historical audit actor references remain useful.
        return False


admin.site.site_header = "Operations Platform Administration"
admin.site.site_title = "Operations Platform Admin"
admin.site.index_title = "System administration"
admin.site.site_url = "/app/"
admin.site.empty_value_display = "—"
