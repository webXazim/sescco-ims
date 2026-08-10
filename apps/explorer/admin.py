from django.contrib import admin

from .models import SavedView, TablePreference


@admin.register(SavedView)
class SavedViewAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "view_type", "updated_at", "created_at")
    list_filter = ("view_type", "updated_at", "created_at")
    search_fields = ("name", "owner__username", "owner__first_name", "owner__last_name")
    readonly_fields = ("query_params", "created_at", "updated_at")
    autocomplete_fields = ("owner",)
    ordering = ("-updated_at", "name")
    list_select_related = ("owner",)
    list_per_page = 50
    fieldsets = (
        ("Saved view", {"fields": ("name", "owner", "view_type")}),
        (
            "Stored filters and columns",
            {
                "fields": ("query_params",),
                "description": "The stored query is read-only. Re-save the view from the workspace to change it.",
            },
        ),
        (
            "Audit information",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(TablePreference)
class TablePreferenceAdmin(admin.ModelAdmin):
    list_display = ("owner", "view_type", "updated_at")
    list_filter = ("view_type", "updated_at")
    search_fields = ("owner__username", "owner__first_name", "owner__last_name")
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("owner",)
