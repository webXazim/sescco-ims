from django.conf import settings
from django.urls import NoReverseMatch, reverse

INVENTORY_BREADCRUMB_PARENTS = {
    "inventory:approval_detail": ("Stock approvals", "inventory:approval_list"),
    "inventory:approval_decide": ("Stock approvals", "inventory:approval_list"),
    "inventory:approval_cancel": ("Stock approvals", "inventory:approval_list"),
    "inventory:detail": ("Inventory Explorer", "inventory:list"),
    "inventory:edit": ("Inventory Explorer", "inventory:list"),
    "inventory:status": ("Inventory Explorer", "inventory:list"),
    "inventory:delete": ("Inventory Explorer", "inventory:list"),
    "inventory:adjust": ("Inventory Explorer", "inventory:list"),
    "inventory:office_add": ("Office stock", "inventory:office"),
    "inventory:transfer_create": ("Transfers", "inventory:transfer_list"),
    "inventory:transfer_detail": ("Transfers", "inventory:transfer_list"),
    "inventory:transfer_reverse": ("Transfers", "inventory:transfer_list"),
    "inventory:movement_detail": ("Activity", "core:activity"),
    "inventory:movement_reverse": ("Activity", "core:activity"),
    "inventory:unit_edit": ("Units", "inventory:units"),
    "inventory:unit_status": ("Units", "inventory:units"),
    "inventory:unit_delete": ("Units", "inventory:units"),
    "inventory:supplier_edit": ("Suppliers", "inventory:suppliers"),
    "inventory:supplier_status": ("Suppliers", "inventory:suppliers"),
    "inventory:supplier_delete": ("Suppliers", "inventory:suppliers"),
    "inventory:location_status": ("Inventory locations", "inventory:locations"),
    "inventory:location_delete": ("Inventory locations", "inventory:locations"),
    "projects:create": ("Projects", "projects:list"),
    "projects:detail": ("Projects", "projects:list"),
    "projects:edit": ("Projects", "projects:list"),
    "projects:status": ("Projects", "projects:list"),
    "projects:delete": ("Projects", "projects:list"),
    "data_exchange:legacy_import": ("Excel imports", "data_exchange:import_list"),
    "data_exchange:opening_import": ("Excel imports", "data_exchange:import_list"),
    "data_exchange:import_detail": ("Excel imports", "data_exchange:import_list"),
    "data_exchange:import_confirm": ("Excel imports", "data_exchange:import_list"),
    "data_exchange:transfer_workbook": ("Office stock", "inventory:office"),
    "explorer:saved_view_open": ("Saved views", "explorer:saved_views"),
    "explorer:saved_view_rename": ("Saved views", "explorer:saved_views"),
    "explorer:saved_view_delete": ("Saved views", "explorer:saved_views"),
}

INVENTORY_BREADCRUMB_FALLBACKS = {
    "inventory:transfer_reverse": "Reverse transfer",
    "inventory:movement_reverse": "Reverse movement",
    "inventory:location_status": "Update inventory location",
    "inventory:location_delete": "Delete inventory location",
}


def _inventory_breadcrumb_context(request):
    match = getattr(request, "resolver_match", None)
    view_name = getattr(match, "view_name", "") or ""
    parent = INVENTORY_BREADCRUMB_PARENTS.get(view_name)
    parent_context = None
    if parent:
        label, route_name = parent
        try:
            parent_context = {"label": label, "url": reverse(route_name)}
        except NoReverseMatch:
            parent_context = None
    return {
        "INVENTORY_BREADCRUMB_PARENT": parent_context,
        "INVENTORY_BREADCRUMB_CURRENT": INVENTORY_BREADCRUMB_FALLBACKS.get(
            view_name, "Inventory workspace"
        ),
    }


def application_context(request):
    company = getattr(request, "company", None)
    membership = getattr(request, "company_membership", None)
    context = {
        "APP_NAME": settings.APP_NAME,
        "APP_SUBTITLE": settings.APP_SUBTITLE,
        "APP_VERSION": settings.APP_VERSION,
        "SINGLE_COMPANY_MODE": settings.SINGLE_COMPANY_MODE,
        "PRIMARY_COMPANY_SLUG": settings.PRIMARY_COMPANY_SLUG,
        "ACTIVE_COMPANY": company,
        "ACTIVE_COMPANY_SETTINGS": getattr(company, "settings", None)
        if company is not None
        else None,
        "ACTIVE_COMPANY_MEMBERSHIP": membership,
        "AVAILABLE_COMPANY_MEMBERSHIPS": (),
        "ACCESS_CONTEXT": {},
        "PLATFORM_CONTEXT": {},
        "NAV_STOCK_APPROVALS_COUNT": 0,
        **_inventory_breadcrumb_context(request),
    }
    if request.user.is_authenticated:
        from apps.accounts.context import access_context_for_request, platform_context_for_request
        from apps.accounts.selectors import active_memberships_for_user

        if not settings.SINGLE_COMPANY_MODE:
            context["AVAILABLE_COMPANY_MEMBERSHIPS"] = active_memberships_for_user(request.user)
        context["ACCESS_CONTEXT"] = access_context_for_request(request)
        context["PLATFORM_CONTEXT"] = platform_context_for_request(request)

        # Inventory navigation counters belong to the Inventory area only. Avoid adding several
        # stock/archive queries to every Payroll, document-print, or Django-admin request.
        if company is None or context["PLATFORM_CONTEXT"].get("current_module") != "inventory":
            context["NAV_LOW_STOCK_COUNT"] = 0
            context["NAV_ARCHIVE_COUNT"] = 0
            context["NAV_TRASH_COUNT"] = 0
            return context

        from apps.accounts.access_catalog import AccessPermission
        from apps.accounts.access_policy import membership_has_permission
        from apps.inventory.services.approvals import pending_visible_request_count

        context["NAV_STOCK_APPROVALS_COUNT"] = pending_visible_request_count(
            company=company,
            user=request.user,
            membership=membership,
        )
        from apps.core.trash import active_trash
        from apps.inventory.access import (
            restrict_inventory_location_queryset,
            restrict_inventory_projects,
            restrict_inventory_stock,
        )
        from apps.inventory.models import InventoryLocation, StockItem, Supplier, Unit
        from apps.inventory.selectors import low_stock_items
        from apps.projects.models import Project

        context["NAV_LOW_STOCK_COUNT"] = restrict_inventory_stock(
            low_stock_items(company), membership
        ).count()
        if membership_has_permission(membership, AccessPermission.SHARED_ARCHIVE_VIEW):
            context["NAV_ARCHIVE_COUNT"] = (
                restrict_inventory_stock(
                    StockItem.objects.for_company(company).filter(
                        status=StockItem.Status.ARCHIVED,
                        deleted_at__isnull=True,
                        project__deleted_at__isnull=True,
                    ),
                    membership,
                ).count()
                + restrict_inventory_projects(
                    Project.objects.for_company(company).filter(
                        status=Project.Status.ARCHIVED, deleted_at__isnull=True
                    ),
                    membership,
                ).count()
                + Unit.objects.for_company(company)
                .filter(archived_at__isnull=False, deleted_at__isnull=True)
                .count()
                + Supplier.objects.for_company(company)
                .filter(archived_at__isnull=False, deleted_at__isnull=True)
                .count()
                + restrict_inventory_location_queryset(
                    InventoryLocation.objects.for_company(company).filter(
                        archived_at__isnull=False, deleted_at__isnull=True
                    ),
                    membership,
                ).count()
            )
        else:
            context["NAV_ARCHIVE_COUNT"] = 0
        if membership_has_permission(membership, AccessPermission.SHARED_TRASH_VIEW):
            context["NAV_TRASH_COUNT"] = (
                restrict_inventory_stock(
                    active_trash(StockItem.objects.for_company(company)), membership
                ).count()
                + restrict_inventory_projects(
                    active_trash(Project.objects.for_company(company)), membership
                ).count()
                + active_trash(Unit.objects.for_company(company)).count()
                + active_trash(Supplier.objects.for_company(company)).count()
                + restrict_inventory_location_queryset(
                    active_trash(InventoryLocation.objects.for_company(company)), membership
                ).count()
            )
        else:
            context["NAV_TRASH_COUNT"] = 0
    else:
        context["NAV_LOW_STOCK_COUNT"] = 0
        context["NAV_ARCHIVE_COUNT"] = 0
        context["NAV_TRASH_COUNT"] = 0
    return context
