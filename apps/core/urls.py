from django.urls import path

from apps.inventory.views import StockAdditionView, StockMovementListView, StockUsageView

from .views import DashboardView, health_check, liveness_check, readiness_check

app_name = "core"

urlpatterns = [
    path("health/", health_check, name="health"),
    path("health/live/", liveness_check, name="health_live"),
    path("health/ready/", readiness_check, name="health_ready"),
    path("", DashboardView.as_view(), name="dashboard"),
    path("activity/", StockMovementListView.as_view(), name="activity"),
    path("stock/add/", StockAdditionView.as_view(), name="add_stock"),
    path("stock/use/", StockUsageView.as_view(), name="remove_stock"),
]
