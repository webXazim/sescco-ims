from urllib.parse import urlencode

from django.contrib import admin
from django.db.models import Count, F, Q
from django.urls import reverse
from django.utils.html import format_html

from .models import StockDocument, StockItem, StockMovement, Supplier, Unit


@admin.register(StockDocument)
class StockDocumentAdmin(admin.ModelAdmin):
    list_display = ("original_name", "stock_item", "uploaded_by", "uploaded_at")
    search_fields = (
        "original_name",
        "reference",
        "stock_item__reference",
        "stock_item__project__code",
        "stock_item__material_name",
        "uploaded_by__username",
    )
    list_filter = ("uploaded_at", "stock_item__project", "uploaded_by")
    readonly_fields = (
        "reference",
        "stock_item",
        "file",
        "original_name",
        "uploaded_by",
        "uploaded_at",
    )
    date_hierarchy = "uploaded_at"
    list_select_related = ("stock_item", "stock_item__project", "uploaded_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockStatusAdminFilter(admin.SimpleListFilter):
    title = "stock level"
    parameter_name = "stock_level"

    def lookups(self, request, model_admin):
        return (("in", "In stock"), ("low", "Low stock"), ("out", "Out of stock"))

    def queryset(self, request, queryset):
        if self.value() == "out":
            return queryset.filter(current_quantity=0)
        if self.value() == "low":
            return queryset.filter(
                minimum_quantity__gt=0,
                current_quantity__gt=0,
                current_quantity__lte=F("minimum_quantity"),
            )
        if self.value() == "in":
            return queryset.filter(current_quantity__gt=0).exclude(
                minimum_quantity__gt=0,
                current_quantity__lte=F("minimum_quantity"),
            )
        return queryset


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "is_active", "active_stock_count", "inventory_link")
    list_filter = ("is_active",)
    search_fields = ("name", "symbol", "normalized_name", "normalized_symbol")
    readonly_fields = (
        "inventory_link",
        "stock_record_count",
        "normalized_name",
        "normalized_symbol",
        "created_at",
        "updated_at",
    )
    ordering = ("name",)
    list_per_page = 50
    fieldsets = (
        ("Unit", {"fields": (("name", "symbol"), "is_active")}),
        ("Inventory usage", {"fields": ("inventory_link", "stock_record_count")}),
        (
            "System information",
            {
                "fields": (
                    "normalized_name",
                    "normalized_symbol",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _stock_record_count=Count("stock_items", distinct=True),
            _active_stock_count=Count(
                "stock_items",
                filter=Q(stock_items__status=StockItem.Status.ACTIVE),
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
        url = f'{reverse("inventory:list")}?{urlencode({"unit": obj.pk})}'
        return format_html('<a href="{}">Open inventory</a>', url)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "location", "is_active", "updated_at")
    list_filter = ("is_active", "location")
    search_fields = ("name", "phone", "normalized_name", "normalized_phone", "location")
    readonly_fields = ("normalized_name", "normalized_phone", "created_at", "updated_at")
    ordering = ("name", "phone")
    list_per_page = 50
    fieldsets = (
        ("Supplier", {"fields": (("name", "phone"), "location", "is_active", "notes")}),
        ("System information", {"fields": ("normalized_name", "normalized_phone", "created_at", "updated_at"), "classes": ("collapse",)}),
    )

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = (
        "material_name",
        "project",
        "supplier_name",
        "unit",
        "current_quantity",
        "minimum_quantity",
        "stock_status_admin",
        "status",
        "movement_count",
        "updated_at",
    )
    list_filter = (
        StockStatusAdminFilter,
        "status",
        "project",
        "unit",
        "latest_addition_date",
    )
    search_fields = (
        "reference",
        "project__code",
        "project__name",
        "material_name",
        "description",
        "supplier_name",
        "supplier_phone",
        "normalized_supplier_phone",
        "supplier_location",
        "notes",
    )
    autocomplete_fields = ("project", "unit")
    readonly_fields = (
        "workspace_actions",
        "movement_history_link",
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
    list_select_related = ("project", "unit")
    date_hierarchy = "created_at"
    list_per_page = 50
    show_full_result_count = False
    fieldsets = (
        (
            "Workspace actions",
            {
                "fields": ("workspace_actions", "movement_history_link"),
                "description": (
                    "Balances and lifecycle changes are controlled by the inventory "
                    "workspace so every change keeps an audit trail."
                ),
            },
        ),
        ("Stock identity", {"fields": ("project", "material_name", "description", "unit")}),
        (
            "Supplier",
            {"fields": ("supplier_name", "supplier_phone", "supplier_location")},
        ),
        ("Stock settings", {"fields": ("minimum_quantity", "notes")}),
        (
            "Live balance (read only)",
            {
                "fields": (
                    "current_quantity",
                    "latest_unit_price",
                    "latest_addition_date",
                    "status",
                )
            },
        ),
        (
            "System and audit information",
            {
                "fields": (
                    "reference",
                    "normalized_material_name",
                    "normalized_supplier_name",
                    "normalized_supplier_phone",
                    "created_by",
                    "created_at",
                    "updated_by",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_movement_count=Count("movements"))

    @admin.display(description="Stock level", ordering="current_quantity")
    def stock_status_admin(self, obj):
        colors = {"in": ("#176b45", "#e9f6ef"), "low": ("#8a5a00", "#fff5d9"), "out": ("#a12a2a", "#fdecec")}
        foreground, background = colors[obj.stock_status]
        return format_html(
            '<span style="color:{};background:{};padding:3px 7px;border-radius:10px">{}</span>',
            foreground,
            background,
            obj.stock_status_label,
        )

    @admin.display(description="Movements", ordering="_movement_count")
    def movement_count(self, obj):
        return obj._movement_count

    @admin.display(description="Movement history")
    def movement_history_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("admin:inventory_stockmovement_changelist")
        return format_html(
            '<a href="{}?{}">View {} movement(s)</a>',
            url,
            urlencode({"stock_item__id__exact": obj.pk}),
            obj.movements.count(),
        )

    @admin.display(description="Open safe controls")
    def workspace_actions(self, obj):
        if not obj or not obj.pk:
            return "—"
        detail = reverse("inventory:detail", kwargs={"reference": obj.reference})
        add = f'{reverse("core:add_stock")}?{urlencode({"project": obj.project.code})}'
        use = f'{reverse("core:remove_stock")}?{urlencode({"stock": obj.reference})}'
        adjust = reverse("inventory:adjust", kwargs={"reference": obj.reference})
        return format_html(
            '<a class="button" href="{}">Open record</a> '
            '<a class="button" href="{}">Add stock</a> '
            '<a class="button" href="{}">Use stock</a> '
            '<a class="button" href="{}">Adjust safely</a>',
            detail,
            add,
            use,
            adjust,
        )

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.movements.exists():
            fields.extend(("project", "unit"))
        return tuple(dict.fromkeys(fields))

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def view_on_site(self, obj):
        return reverse("inventory:detail", kwargs={"reference": obj.reference})

    def has_add_permission(self, request):
        return False

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
    list_filter = ("movement_type", "movement_date", "stock_item__project", "created_by")
    search_fields = (
        "reference",
        "stock_item__reference",
        "stock_item__project__code",
        "stock_item__material_name",
        "project_code_snapshot",
        "project_name_snapshot",
        "material_name_snapshot",
        "supplier_name_snapshot",
        "supplier_phone_snapshot",
        "supplier_phone_normalized_snapshot",
        "invoice_reference",
        "purpose",
        "recipient",
        "reason",
        "notes",
        "created_by__username",
    )
    readonly_fields = (
        "workspace_movement_link",
        "reversal_action",
        "reference",
        "idempotency_key",
        "stock_item",
        "movement_type",
        "movement_date",
        "quantity",
        "previous_balance",
        "new_balance",
        "unit_price",
        "invoice_reference",
        "purpose",
        "recipient",
        "reason",
        "notes",
        "attachment",
        "reversal_of",
        "project_code_snapshot",
        "project_name_snapshot",
        "material_name_snapshot",
        "supplier_name_snapshot",
        "supplier_phone_snapshot",
        "supplier_phone_normalized_snapshot",
        "unit_symbol_snapshot",
        "created_by",
        "created_at",
    )
    date_hierarchy = "movement_date"
    list_select_related = ("stock_item", "stock_item__project", "stock_item__unit", "created_by")
    ordering = ("-movement_date", "-created_at")
    list_per_page = 75
    show_full_result_count = False
    fieldsets = (
        ("Workspace", {"fields": ("workspace_movement_link", "reversal_action")}),
        (
            "Movement",
            {
                "fields": (
                    "stock_item",
                    ("movement_type", "movement_date"),
                    ("quantity", "unit_price"),
                    ("previous_balance", "new_balance"),
                )
            },
        ),
        (
            "Business details",
            {"fields": ("invoice_reference", "purpose", "recipient", "reason", "notes", "attachment")},
        ),
        (
            "Recorded identity snapshot",
            {
                "fields": (
                    ("project_code_snapshot", "project_name_snapshot"),
                    "material_name_snapshot",
                    "supplier_name_snapshot",
                    ("supplier_phone_snapshot", "supplier_phone_normalized_snapshot"),
                    "unit_symbol_snapshot",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Audit information",
            {
                "fields": ("reference", "idempotency_key", "reversal_of", "created_by", "created_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Project", ordering="project_code_snapshot")
    def project_snapshot_admin(self, obj):
        return obj.project_code_display

    @admin.display(description="Material", ordering="material_name_snapshot")
    def material_snapshot_admin(self, obj):
        return obj.material_name_display

    @admin.display(description="Quantity", ordering="quantity")
    def signed_quantity_admin(self, obj):
        color = "#176b45" if obj.is_inbound else "#a12a2a"
        return format_html('<strong style="color:{}">{}</strong>', color, obj.signed_quantity_display)

    @admin.display(description="Status")
    def reversal_status(self, obj):
        if obj.movement_type == StockMovement.Type.REVERSAL:
            return "Reversal"
        return "Reversed" if obj.is_reversed else "Active"

    @admin.display(description="Correction")
    def reversal_action(self, obj):
        if not obj or not obj.pk or obj.movement_type == StockMovement.Type.REVERSAL or obj.is_reversed:
            return "—"
        url = reverse("inventory:movement_reverse", kwargs={"reference": obj.reference})
        return format_html('<a class="button" href="{}">Reverse safely</a>', url)

    @admin.display(description="Workspace record")
    def workspace_movement_link(self, obj):
        if not obj or not obj.pk:
            return "—"
        url = reverse("inventory:movement_detail", kwargs={"reference": obj.reference})
        return format_html('<a href="{}">Open movement details</a>', url)

    def view_on_site(self, obj):
        return reverse("inventory:movement_detail", kwargs={"reference": obj.reference})

    def lookup_allowed(self, lookup, value, request=None):
        if lookup == "stock_item__id__exact":
            return True
        return super().lookup_allowed(lookup, value, request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
