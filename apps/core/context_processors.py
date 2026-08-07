from django.conf import settings


def application_context(request):
    context = {
        "APP_NAME": settings.APP_NAME,
        "APP_SUBTITLE": settings.APP_SUBTITLE,
        "APP_VERSION": settings.APP_VERSION,
    }
    if request.user.is_authenticated:
        from apps.inventory.selectors import low_stock_items

        context["NAV_LOW_STOCK_COUNT"] = low_stock_items().count()
    else:
        context["NAV_LOW_STOCK_COUNT"] = 0
    return context
