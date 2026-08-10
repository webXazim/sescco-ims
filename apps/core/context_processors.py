from django.conf import settings


def application_context(request):
    context = {
        "APP_NAME": settings.APP_NAME,
        "APP_SUBTITLE": settings.APP_SUBTITLE,
        "APP_VERSION": settings.APP_VERSION,
    }
    if request.user.is_authenticated:
        from apps.core.trash import active_trash
        from apps.inventory.models import StockItem, Supplier, Unit
        from apps.inventory.selectors import low_stock_items
        from apps.projects.models import Project

        context["NAV_LOW_STOCK_COUNT"] = low_stock_items().count()
        context["NAV_ARCHIVE_COUNT"] = (
            StockItem.objects.filter(
                status=StockItem.Status.ARCHIVED,
                deleted_at__isnull=True,
                project__deleted_at__isnull=True,
            ).count()
            + Project.objects.filter(
                status=Project.Status.ARCHIVED, deleted_at__isnull=True
            ).count()
            + Unit.objects.filter(is_active=False, deleted_at__isnull=True).count()
            + Supplier.objects.filter(is_active=False, deleted_at__isnull=True).count()
        )
        context["NAV_TRASH_COUNT"] = (
            active_trash(StockItem.objects.all()).count()
            + active_trash(Project.objects.all()).count()
            + active_trash(Unit.objects.all()).count()
            + active_trash(Supplier.objects.all()).count()
        )
    else:
        context["NAV_LOW_STOCK_COUNT"] = 0
        context["NAV_ARCHIVE_COUNT"] = 0
        context["NAV_TRASH_COUNT"] = 0
    return context
