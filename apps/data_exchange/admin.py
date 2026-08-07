from urllib.parse import urlencode

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import ExportAudit, ImportJob, ImportRow


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "import_type",
        "status",
        "total_rows",
        "imported_rows",
        "error_rows",
        "created_by",
        "created_at",
        "workspace_link",
    )
    list_filter = ("import_type", "status", "created_at", "created_by")
    search_fields = (
        "original_filename",
        "reference",
        "project__code",
        "created_by__username",
        "error_message",
    )
    readonly_fields = (
        "workspace_link",
        "rows_link",
        "reference",
        "import_type",
        "status",
        "source_file",
        "original_filename",
        "project",
        "default_unit",
        "options",
        "total_rows",
        "valid_rows",
        "warning_rows",
        "error_rows",
        "imported_rows",
        "skipped_rows",
        "error_message",
        "created_by",
        "created_at",
        "confirmed_at",
    )
    list_select_related = ("project", "default_unit", "created_by")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 50
    show_full_result_count = False
    fieldsets = (
        ("Import workspace", {"fields": ("workspace_link", "rows_link")}),
        (
            "Import summary",
            {
                "fields": (
                    ("import_type", "status"),
                    "original_filename",
                    "source_file",
                    ("project", "default_unit"),
                )
            },
        ),
        (
            "Row results",
            {
                "fields": (
                    "total_rows",
                    ("valid_rows", "warning_rows", "error_rows"),
                    ("imported_rows", "skipped_rows"),
                    "error_message",
                )
            },
        ),
        ("Options", {"fields": ("options",), "classes": ("collapse",)}),
        (
            "Audit information",
            {
                "fields": ("reference", "created_by", "created_at", "confirmed_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Workspace")
    def workspace_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("data_exchange:import_detail", kwargs={"reference": obj.reference})
        return format_html('<a href="{}">Review import</a>', url)

    @admin.display(description="Parsed rows")
    def rows_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:data_exchange_importrow_changelist")
        return format_html(
            '<a href="{}?{}">Browse {} row(s)</a>',
            url,
            urlencode({"job__id__exact": obj.pk}),
            obj.total_rows,
        )

    def view_on_site(self, obj):
        return reverse("data_exchange:import_detail", kwargs={"reference": obj.reference})

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = (
        "job",
        "row_number",
        "status",
        "planned_action",
        "requires_confirmation",
        "imported_stock_item",
        "processed_at",
    )
    list_filter = ("status", "planned_action", "requires_confirmation", "job__import_type")
    search_fields = (
        "job__original_filename",
        "job__reference",
        "message",
        "imported_stock_item__material_name",
        "imported_stock_item__project__code",
    )
    readonly_fields = tuple(field.name for field in ImportRow._meta.fields)
    list_select_related = ("job", "imported_stock_item", "movement")
    ordering = ("job", "row_number")
    list_per_page = 100
    show_full_result_count = False
    fieldsets = (
        ("Row result", {"fields": ("job", "row_number", "status", "planned_action", "message")}),
        (
            "Matches and output",
            {
                "fields": (
                    "requires_confirmation",
                    "exact_match",
                    "similar_match_ids",
                    "imported_stock_item",
                    "movement",
                    "processed_at",
                )
            },
        ),
        ("Source data", {"fields": ("raw_data", "cleaned_data"), "classes": ("collapse",)}),
    )

    def lookup_allowed(self, lookup, value, request=None):
        if lookup == "job__id__exact":
            return True
        return super().lookup_allowed(lookup, value, request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExportAudit)
class ExportAuditAdmin(admin.ModelAdmin):
    list_display = (
        "dataset",
        "file_format",
        "row_count",
        "scope_label",
        "created_by",
        "created_at",
    )
    list_filter = ("dataset", "file_format", "created_at", "created_by")
    search_fields = (
        "reference",
        "scope_label",
        "scope_reference",
        "created_by__username",
    )
    readonly_fields = tuple(field.name for field in ExportAudit._meta.fields)
    list_select_related = ("created_by",)
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_per_page = 75
    show_full_result_count = False
    fieldsets = (
        (
            "Export summary",
            {"fields": (("dataset", "file_format"), "row_count", "scope_label", "scope_reference")},
        ),
        ("Applied view", {"fields": ("filters", "columns", "sort"), "classes": ("collapse",)}),
        (
            "Audit information",
            {"fields": ("reference", "created_by", "created_at"), "classes": ("collapse",)},
        ),
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
