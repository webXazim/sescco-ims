from django.contrib import admin

from .models import AuditEvent, Company, CompanySettings, NumberSequence


class ReadOnlyPlatformAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Company)
class CompanyAdmin(ReadOnlyPlatformAdmin):
    list_display = ("name", "legal_name", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "legal_name", "slug")
    readonly_fields = ("id", "name", "legal_name", "slug", "is_active", "created_at", "updated_at")
    ordering = ("name",)


@admin.register(CompanySettings)
class CompanySettingsAdmin(ReadOnlyPlatformAdmin):
    list_display = ("company", "timezone", "currency_code", "country_code", "updated_at")
    search_fields = ("company__name", "company__legal_name", "company__slug")
    readonly_fields = ("id", "company", "timezone", "currency_code", "country_code", "created_at", "updated_at")


@admin.register(NumberSequence)
class NumberSequenceAdmin(ReadOnlyPlatformAdmin):
    list_display = ("company", "key", "prefix", "padding", "next_value", "last_issued_value", "updated_at")
    list_filter = ("company",)
    search_fields = ("company__name", "key", "prefix")
    readonly_fields = (
        "id", "company", "key", "prefix", "padding", "next_value", "last_issued_value", "created_at", "updated_at",
    )


@admin.register(AuditEvent)
class AuditEventAdmin(ReadOnlyPlatformAdmin):
    list_display = ("created_at", "company", "area", "action", "object_type", "object_id", "actor_username")
    list_filter = ("area", "company", "created_at")
    search_fields = (
        "action", "object_type", "object_id", "object_label", "actor_username", "actor_display_name", "actor_email",
    )
    readonly_fields = tuple(field.name for field in AuditEvent._meta.fields)
    date_hierarchy = "created_at"
