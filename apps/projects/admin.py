from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "client_name",
        "location",
        "status",
        "active_stock_count",
        "inventory_link",
        "updated_at",
    )
    list_filter = ("status", "start_date", "expected_completion_date")
    search_fields = ("code", "name", "client_name", "location")
    readonly_fields = (
        "inventory_link",
        "stock_record_count",
        "active_stock_count",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    ordering = ("code",)
    date_hierarchy = "created_at"
    list_per_page = 50
    fieldsets = (
        ("Project identity", {"fields": ("code", "name", "client_name", "location")}),
        (
            "Schedule and lifecycle",
            {"fields": ("status", ("start_date", "expected_completion_date"))},
        ),
        ("Notes", {"fields": ("notes",)}),
        (
            "Inventory summary",
            {
                "fields": ("inventory_link", "stock_record_count", "active_stock_count"),
                "description": "Stock activity must be performed in the inventory workspace.",
            },
        ),
        (
            "Audit information",
            {
                "fields": ("created_by", "created_at", "updated_by", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _stock_record_count=Count("stock_items", distinct=True),
            _active_stock_count=Count(
                "stock_items",
                filter=Q(stock_items__status="active"),
                distinct=True,
            ),
        )

    @admin.display(description="Stock records", ordering="_stock_record_count")
    def stock_record_count(self, obj):
        return obj._stock_record_count

    @admin.display(description="Active stock", ordering="_active_stock_count")
    def active_stock_count(self, obj):
        return obj._active_stock_count

    @admin.display(description="Workspace")
    def inventory_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = f'{reverse("inventory:list")}?project={obj.code}'
        return format_html('<a href="{}">Open inventory</a>', url)

    def view_on_site(self, obj):
        return reverse("projects:detail", kwargs={"code": obj.code})

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False
