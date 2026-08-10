from decimal import Decimal

from django.conf import settings
from django.db import connection, models
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.views.generic import TemplateView

from apps.inventory.models import StockItem, StockMovement, Unit
from apps.inventory.selectors import (
    LOW_STOCK_CONDITION,
    stock_items,
    stock_movements,
)
from apps.projects.models import Project

from .access import InventoryWorkspaceMixin


def _compact_value(value: Decimal) -> str:
    absolute = abs(value)
    if absolute >= Decimal("1000000000000000000"):
        return f"{value:.3E}"
    for threshold, suffix in (
        (Decimal("1000000000000000"), "Q"),
        (Decimal("1000000000000"), "T"),
        (Decimal("1000000000"), "B"),
        (Decimal("1000000"), "M"),
        (Decimal("1000"), "K"),
    ):
        if absolute >= threshold:
            return f"{value / threshold:,.2f}{suffix}"
    return f"{value:,.2f}"


class WorkspaceTemplateView(InventoryWorkspaceMixin, TemplateView):
    page_key = ""
    page_title = ""
    page_subtitle = ""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key=self.page_key,
            page_title=self.page_title,
            page_subtitle=self.page_subtitle,
        )
        return context


class DashboardView(WorkspaceTemplateView):
    template_name = "core/dashboard.html"
    page_key = "dashboard"
    page_title = "Inventory overview"
    page_subtitle = "Current stock and recent movements across contracting projects."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_project = self.request.GET.get("project", "").strip()
        items = stock_items().filter(status=StockItem.Status.ACTIVE)
        movements = stock_movements()
        projects = Project.objects.order_by("code")
        selected_project_object = None
        if selected_project:
            selected_project_object = projects.filter(code=selected_project).first()
            if selected_project_object:
                items = items.filter(project=selected_project_object)
                movements = movements.filter(stock_item__project=selected_project_object)
            else:
                selected_project = ""

        project_summaries = Project.objects.filter(status=Project.Status.ACTIVE)
        if selected_project_object:
            project_summaries = project_summaries.filter(pk=selected_project_object.pk)

        today = timezone.localdate()
        value_field = DecimalField(max_digits=32, decimal_places=5)
        stock_value = ExpressionWrapper(
            F("current_quantity") * F("latest_unit_price"),
            output_field=value_field,
        )
        movement_value = ExpressionWrapper(
            F("quantity") * F("unit_price"),
            output_field=value_field,
        )
        inbound_today = movements.filter(
            movement_date=today,
            movement_type__in=(
                StockMovement.Type.OPENING,
                StockMovement.Type.ADDITION,
                StockMovement.Type.ADJUSTMENT_IN,
            ),
        )
        outbound_today = movements.filter(
            movement_date=today,
            movement_type__in=(
                StockMovement.Type.USAGE,
                StockMovement.Type.ADJUSTMENT_OUT,
            ),
        )
        zero_value = Value(Decimal("0"), output_field=value_field)
        inventory_value = items.aggregate(
            value=Coalesce(Sum(stock_value), zero_value, output_field=value_field)
        )["value"]
        added_today_value = inbound_today.aggregate(
            value=Coalesce(Sum(movement_value), zero_value, output_field=value_field)
        )["value"]
        used_today_value = outbound_today.aggregate(
            value=Coalesce(Sum(movement_value), zero_value, output_field=value_field)
        )["value"]
        context.update(
            projects=projects,
            selected_project=selected_project,
            selected_project_object=selected_project_object,
            active_project_count=Project.objects.filter(status=Project.Status.ACTIVE).count(),
            stock_record_count=items.count(),
            low_stock_count=items.filter(status=StockItem.Status.ACTIVE)
            .filter(LOW_STOCK_CONDITION)
            .count(),
            out_of_stock_count=items.filter(
                status=StockItem.Status.ACTIVE, current_quantity=0
            ).count(),
            unit_count=Unit.objects.filter(is_active=True).count(),
            inventory_value=inventory_value,
            inventory_value_compact=_compact_value(inventory_value),
            unpriced_stock_count=items.filter(
                current_quantity__gt=0, latest_unit_price__isnull=True
            ).count(),
            stock_added_today=inbound_today.count(),
            stock_added_today_value=added_today_value,
            stock_added_today_value_compact=_compact_value(added_today_value),
            stock_added_today_unpriced=inbound_today.filter(unit_price__isnull=True).count(),
            stock_used_today=outbound_today.count(),
            stock_used_today_value=used_today_value,
            stock_used_today_value_compact=_compact_value(used_today_value),
            stock_used_today_unpriced=outbound_today.filter(unit_price__isnull=True).count(),
            recent_movements=movements[:8],
            project_summaries=project_summaries.annotate(
                stock_count=Count(
                    "stock_items",
                    filter=models.Q(stock_items__status=StockItem.Status.ACTIVE),
                )
            ).order_by("-stock_count", "code")[:6],
        )
        return context


@require_GET
@never_cache
def liveness_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "service": "inventory",
            "version": settings.APP_VERSION,
        }
    )


@require_GET
@never_cache
def readiness_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse(
            {
                "status": "unhealthy",
                "service": "inventory",
                "version": settings.APP_VERSION,
                "database": "unavailable",
            },
            status=503,
        )
    return JsonResponse(
        {
            "status": "ok",
            "service": "inventory",
            "version": settings.APP_VERSION,
            "database": "ready",
        }
    )


# Backward-compatible readiness URL used by older deployment scripts.
health_check = readiness_check
