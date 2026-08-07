from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import StockItem, StockMovement, Unit


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "symbol")
    readonly_fields = ("normalized_name", "normalized_symbol", "created_at", "updated_at")
    ordering = ("name",)

    def has_delete_permission(self, request, obj=None):
        return False


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    can_delete = False
    show_change_link = True
    fields = (
        "movement_date",
        "movement_type",
        "project_code_snapshot",
        "project_name_snapshot",
        "material_name_snapshot",
        "supplier_name_snapshot",
        "supplier_phone_snapshot",
        "supplier_phone_normalized_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "previous_balance",
        "new_balance",
        "created_by",
    )
    readonly_fields = fields
    ordering = ("-movement_date", "-created_at")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = (
        "material_name",
        "project",
        "supplier_name",
        "supplier_phone",
        "unit",
        "current_quantity",
        "minimum_quantity",
        "stock_status_admin",
        "status",
        "updated_at",
    )
    list_filter = ("status", "project", "unit", "latest_addition_date")
    search_fields = (
        "project__code",
        "project__name",
        "material_name",
        "description",
        "supplier_name",
        "supplier_phone",
    )
    autocomplete_fields = ("project", "unit")
    readonly_fields = (
        "reference",
        "normalized_material_name",
        "normalized_supplier_name",
        "normalized_supplier_phone",
        "current_quantity",
        "latest_unit_price",
        "latest_addition_date",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    inlines = (StockMovementInline,)
    list_select_related = ("project", "unit")
    date_hierarchy = "created_at"

    @admin.display(description="Stock status")
    def stock_status_admin(self, obj):
        return obj.stock_status_label

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.movements.exists():
            fields.extend(["project", "unit"])
        return tuple(dict.fromkeys(fields))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "movement_date",
        "project_snapshot_admin",
        "material_snapshot_admin",
        "movement_type",
        "signed_quantity_admin",
        "previous_balance",
        "new_balance",
        "created_by",
        "reversal_status",
        "reversal_action",
    )
    list_filter = ("movement_type", "movement_date", "stock_item__project")
    search_fields = (
        "reference",
        "stock_item__project__code",
        "stock_item__material_name",
        "stock_item__supplier_name",
        "stock_item__supplier_phone",
        "project_code_snapshot",
        "material_name_snapshot",
        "supplier_name_snapshot",
        "supplier_phone_snapshot",
        "supplier_phone_normalized_snapshot",
        "invoice_reference",
        "purpose",
        "recipient",
        "reason",
    )
    readonly_fields = (
        "reference",
        "idempotency_key",
        "stock_item",
        "movement_type",
        "project_code_snapshot",
        "project_name_snapshot",
        "material_name_snapshot",
        "supplier_name_snapshot",
        "supplier_phone_snapshot",
        "supplier_phone_normalized_snapshot",
        "unit_symbol_snapshot",
        "quantity",
        "previous_balance",
        "new_balance",
        "unit_price",
        "movement_date",
        "invoice_reference",
        "purpose",
        "recipient",
        "reason",
        "notes",
        "attachment",
        "reversal_of",
        "created_by",
        "created_at",
        "reversal_action",
    )
    date_hierarchy = "movement_date"
    list_select_related = ("stock_item", "stock_item__project", "stock_item__unit", "created_by")
    ordering = ("-movement_date", "-created_at")

    @admin.display(description="Project", ordering="project_code_snapshot")
    def project_snapshot_admin(self, obj):
        return obj.project_code_display

    @admin.display(description="Material", ordering="material_name_snapshot")
    def material_snapshot_admin(self, obj):
        return obj.material_name_display

    @admin.display(description="Quantity")
    def signed_quantity_admin(self, obj):
        return obj.signed_quantity_display

    @admin.display(description="Status")
    def reversal_status(self, obj):
        if obj.movement_type == StockMovement.Type.REVERSAL:
            return "Reversal"
        return "Reversed" if obj.is_reversed else "Active"

    @admin.display(description="Correction")
    def reversal_action(self, obj):
        if not obj.pk or obj.movement_type == StockMovement.Type.REVERSAL or obj.is_reversed:
            return "—"
        url = reverse("inventory:movement_reverse", kwargs={"reference": obj.reference})
        return format_html('<a class="button" href="{}">Reverse safely</a>', url)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
