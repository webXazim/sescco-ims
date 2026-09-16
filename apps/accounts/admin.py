from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import ValidationError

from .models import AccessProfile, AccessProfilePermission, CompanyMembership, User
from .security import bump_user_security_version


class CompanyMembershipInline(admin.TabularInline):
    model = CompanyMembership
    extra = 0
    fields = ("company", "role", "access_profile", "project_scope_mode", "branch_scope_mode", "inventory_location_scope_mode", "is_active", "joined_at")
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
        "is_active",
        "must_change_password",
        "is_superuser",
        "last_login",
    )
    list_filter = ("is_active", "is_superuser")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
    list_per_page = 50
    readonly_fields = ("is_staff", "last_login", "date_joined", "credentials_updated_at", "security_version")
    fieldsets = (
        ("Account", {"fields": ("username", "password")}),
        ("Profile", {"fields": ("first_name", "last_name", "email")}),
        (
            "Account status",
            {
                "fields": ("is_active", "must_change_password", "credentials_updated_at", "security_version", "is_staff"),
                "description": (
                    "SESCCO application access is assigned through CompanyMembership + AccessProfile. "
                    "Django staff access is reserved for superusers."
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
                "fields": ("username", "password1", "password2", "is_active"),
            },
        ),
    )
    actions = ("activate_accounts", "deactivate_accounts")

    @admin.action(description="Activate selected accounts")
    def activate_accounts(self, request, queryset):
        target_ids = list(queryset.values_list("pk", flat=True))
        count = queryset.update(is_active=True)
        for user_id in target_ids:
            bump_user_security_version(user_id)
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
                account.save(update_fields=("is_active", "is_staff"))
            except ValidationError:
                protected += 1
                continue
            bump_user_security_version(account.pk)
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
    list_display = ("user", "company", "role", "access_profile", "is_active", "joined_at")
    list_filter = ("role", "is_active", "company")
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name", "company__name")
    ordering = ("company__name", "user__username")
    readonly_fields = ("id", "joined_at", "created_at", "updated_at")
    list_select_related = ("user", "company", "access_profile")

    def has_add_permission(self, request):
        return bool(request.user.is_superuser)

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def save_model(self, request, obj, form, change):
        security_fields = {"role", "access_profile", "project_scope_mode", "branch_scope_mode", "inventory_location_scope_mode", "is_active"}
        changed_security = bool(change and security_fields.intersection(set(getattr(form, "changed_data", ()))))
        super().save_model(request, obj, form, change)
        if changed_security:
            bump_user_security_version(obj.user_id)

    def has_delete_permission(self, request, obj=None):
        # Access is deactivated rather than deleted so historical audit actor references remain useful.
        return False


class AccessProfilePermissionInline(admin.TabularInline):
    model = AccessProfilePermission
    extra = 0
    fields = ("permission",)
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(AccessProfile)
class AccessProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "key", "is_system", "is_active", "updated_at")
    list_filter = ("is_system", "is_active", "company")
    search_fields = ("name", "key", "description", "company__name")
    readonly_fields = ("id", "company", "key", "name", "description", "is_system", "is_active", "created_at", "updated_at")
    list_select_related = ("company",)
    inlines = (AccessProfilePermissionInline,)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return bool(request.user.is_superuser)

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "SESCCO MS Administration"
admin.site.site_title = "SESCCO MS Admin"
admin.site.index_title = "System administration"
admin.site.site_url = "/app/"
admin.site.empty_value_display = "—"
