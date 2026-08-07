from django.contrib import admin

from .models import ExportAudit, ImportJob, ImportRow


class ImportRowInline(admin.TabularInline):
    model = ImportRow
    extra = 0
    can_delete = False
    fields = (
        "row_number",
        "status",
        "planned_action",
        "message",
        "imported_stock_item",
        "movement",
    )
    readonly_fields = fields
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "import_type",
        "status",
        "total_rows",
        "imported_rows",
        "created_by",
        "created_at",
    )
    list_filter = ("import_type", "status", "created_at")
    search_fields = ("original_filename", "reference", "created_by__username")
    readonly_fields = (
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
    inlines = (ImportRowInline,)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ("job", "row_number", "status", "planned_action", "processed_at")
    list_filter = ("status", "planned_action", "job__import_type")
    search_fields = ("job__original_filename", "message")
    readonly_fields = [field.name for field in ImportRow._meta.fields]

    def has_add_permission(self, request):
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
    list_filter = ("dataset", "file_format", "created_at")
    search_fields = ("scope_label", "scope_reference", "created_by__username")
    readonly_fields = [field.name for field in ExportAudit._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
