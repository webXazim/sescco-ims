from django.contrib import admin
from django.db.models import Count, Q
from django.urls import reverse
from django.utils.html import format_html

from apps.accounts.permissions import membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace

from .forms import ProjectForm
from .models import Project


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    form = ProjectForm

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)
        company = getattr(request, "company", None)

        class CompanyProjectAdminForm(base_form):
            def __init__(self, *args, **form_kwargs):
                form_kwargs.setdefault("company", company)
                super().__init__(*args, **form_kwargs)

        return CompanyProjectAdminForm
    def has_module_permission(self, request):
        return membership_can_workspace(getattr(request, "company_membership", None), Workspace.INVENTORY)

    def has_view_permission(self, request, obj=None):
        return membership_can_workspace(getattr(request, "company_membership", None), Workspace.INVENTORY)

    list_display = (
        "code",
        "name",
        "client_name",
        "location",
        "manager_name",
        "status",
        "active_stock_count",
        "inventory_link",
        "updated_at",
    )
    list_filter = ("status", "start_date", "expected_completion_date", "end_date")
    search_fields = ("code", "name", "client_name", "location", "manager_name", "reference")
    readonly_fields = (
        "reference",
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
        ("Project identity", {"fields": ("reference", "code", "name", "client_name", "location", "manager_name")}),
        (
            "Schedule and lifecycle",
            {"fields": ("status", ("start_date", "expected_completion_date", "end_date"))},
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
        company = getattr(request, "company", None)
        if company is None:
            return super().get_queryset(request).none()
        return super().get_queryset(request).filter(company=company).annotate(
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
        if not obj.company_id:
            obj.company = request.company
        if not obj.created_by_id:
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        if not membership_has_capability(getattr(request, "company_membership", None), Capability.MANAGE_INVENTORY):
            return False
        return obj is None or not (obj.stock_items.exists() or obj.import_jobs.exists())

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions
