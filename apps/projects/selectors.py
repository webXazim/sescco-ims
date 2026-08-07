from django.db.models import Count, F, Max, Q, QuerySet

from .models import Project


def project_list() -> QuerySet[Project]:
    low_condition = (
        Q(stock_items__status="active")
        & Q(stock_items__current_quantity__lte=F("stock_items__minimum_quantity"))
        & (Q(stock_items__minimum_quantity__gt=0) | Q(stock_items__current_quantity=0))
    )
    return Project.objects.annotate(
        stock_record_count=Count("stock_items", distinct=True),
        low_stock_count=Count("stock_items", filter=low_condition, distinct=True),
        last_stock_update=Max("stock_items__updated_at"),
    )


def active_projects() -> QuerySet[Project]:
    return Project.objects.filter(status=Project.Status.ACTIVE).order_by("code")
