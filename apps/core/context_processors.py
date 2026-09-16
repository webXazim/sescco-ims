from django.conf import settings


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
        "ACTIVE_COMPANY_SETTINGS": getattr(company, "settings", None) if company is not None else None,
        "ACTIVE_COMPANY_MEMBERSHIP": membership,
        "AVAILABLE_COMPANY_MEMBERSHIPS": (),
        "ACCESS_CONTEXT": {},
        "PLATFORM_CONTEXT": {},
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
        from apps.accounts.access_control import membership_has_permission
        from apps.core.trash import active_trash
        from apps.inventory.access import (
            restrict_inventory_location_queryset,
            restrict_inventory_stock,
        )
        from apps.inventory.models import InventoryLocation, StockItem, Supplier, Unit
        from apps.inventory.selectors import low_stock_items
        from apps.projects.models import Project
        from apps.inventory.access import restrict_inventory_projects

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
                + Unit.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).count()
                + Supplier.objects.for_company(company).filter(archived_at__isnull=False, deleted_at__isnull=True).count()
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
                restrict_inventory_stock(active_trash(StockItem.objects.for_company(company)), membership).count()
                + restrict_inventory_projects(active_trash(Project.objects.for_company(company)), membership).count()
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
