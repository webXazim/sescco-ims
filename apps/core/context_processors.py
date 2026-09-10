from django.conf import settings


def application_context(request):
    company = getattr(request, "company", None)
    membership = getattr(request, "company_membership", None)
    context = {
        "APP_NAME": settings.APP_NAME,
        "APP_SUBTITLE": settings.APP_SUBTITLE,
        "APP_VERSION": settings.APP_VERSION,
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

        from apps.core.trash import active_trash
        from apps.inventory.models import StockItem, Supplier, Unit
        from apps.inventory.selectors import low_stock_items
        from apps.projects.models import Project

        context["NAV_LOW_STOCK_COUNT"] = low_stock_items(company).count()
        context["NAV_ARCHIVE_COUNT"] = (
            StockItem.objects.for_company(company).filter(
                status=StockItem.Status.ARCHIVED,
                deleted_at__isnull=True,
                project__deleted_at__isnull=True,
            ).count()
            + Project.objects.for_company(company).filter(
                status=Project.Status.ARCHIVED, deleted_at__isnull=True
            ).count()
            + Unit.objects.for_company(company).filter(is_active=False, deleted_at__isnull=True).count()
            + Supplier.objects.for_company(company).filter(is_active=False, deleted_at__isnull=True).count()
        )
        context["NAV_TRASH_COUNT"] = (
            active_trash(StockItem.objects.for_company(company)).count()
            + active_trash(Project.objects.for_company(company)).count()
            + active_trash(Unit.objects.for_company(company)).count()
            + active_trash(Supplier.objects.for_company(company)).count()
        )
    else:
        context["NAV_LOW_STOCK_COUNT"] = 0
        context["NAV_ARCHIVE_COUNT"] = 0
        context["NAV_TRASH_COUNT"] = 0
    return context
