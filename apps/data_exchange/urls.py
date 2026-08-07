from django.urls import path

from .views import (
    ActivityExportView,
    ImportJobConfirmView,
    ImportJobDetailView,
    ImportJobListView,
    ImportSourceFileView,
    InventoryExportView,
    LegacyImportCreateView,
    LowStockExportView,
    OpeningImportCreateView,
    OpeningTemplateView,
    ProjectInventoryExportView,
    StockHistoryExportView,
)

app_name = "data_exchange"

urlpatterns = [
    path(
        "exports/inventory/<str:file_format>/",
        InventoryExportView.as_view(),
        name="inventory_export",
    ),
    path(
        "exports/low-stock/<str:file_format>/",
        LowStockExportView.as_view(),
        name="low_stock_export",
    ),
    path(
        "exports/activity/<str:file_format>/",
        ActivityExportView.as_view(),
        name="activity_export",
    ),
    path(
        "exports/stock/<uuid:reference>/<str:file_format>/",
        StockHistoryExportView.as_view(),
        name="stock_history_export",
    ),
    path(
        "exports/project/<str:code>/<str:file_format>/",
        ProjectInventoryExportView.as_view(),
        name="project_inventory_export",
    ),
    path("imports/", ImportJobListView.as_view(), name="import_list"),
    path("imports/legacy/new/", LegacyImportCreateView.as_view(), name="legacy_import"),
    path("imports/opening/new/", OpeningImportCreateView.as_view(), name="opening_import"),
    path("imports/opening/template/", OpeningTemplateView.as_view(), name="opening_template"),
    path("imports/<uuid:reference>/", ImportJobDetailView.as_view(), name="import_detail"),
    path(
        "imports/<uuid:reference>/confirm/",
        ImportJobConfirmView.as_view(),
        name="import_confirm",
    ),
    path(
        "imports/<uuid:reference>/source/",
        ImportSourceFileView.as_view(),
        name="import_source",
    ),
]
