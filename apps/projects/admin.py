from django.contrib import admin
from django.db.models import Count

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "client_name",
        "location",
        "status",
        "stock_record_count",
        "updated_at",
    )
    list_filter = ("status", "start_date", "expected_completion_date")
    search_fields = ("code", "name", "client_name", "location")
    readonly_fields = ("created_by", "updated_by", "created_at", "updated_at")
    ordering = ("code",)
    date_hierarchy = "created_at"

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_stock_record_count=Count("stock_items"))

    @admin.display(description="Stock records", ordering="_stock_record_count")
    def stock_record_count(self, obj):
        return obj._stock_record_count

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False
