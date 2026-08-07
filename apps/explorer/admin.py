from django.contrib import admin

from .models import SavedView


@admin.register(SavedView)
class SavedViewAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "view_type", "updated_at")
    list_filter = ("view_type", "updated_at")
    search_fields = ("name", "owner__username", "owner__first_name", "owner__last_name")
    readonly_fields = ("query_params", "created_at", "updated_at")
