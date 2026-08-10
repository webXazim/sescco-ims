from django.urls import path

from .views import (
    LowStockListView,
    MovementAttachmentView,
    MovementReversalView,
    StockAdjustmentView,
    StockDocumentAttachmentView,
    StockItemCreateView,
    StockItemDetailView,
    StockItemListView,
    StockItemStatusView,
    StockItemDeleteView,
    StockItemUpdateView,
    StockMatchAPIView,
    StockPickerAPIView,
    StockMovementDetailView,
    SupplierListCreateView,
    SupplierDeleteView,
    SupplierStatusView,
    SupplierUpdateView,
    UnitListCreateView,
    UnitDeleteView,
    UnitStatusView,
    UnitUpdateView,
)

app_name = "inventory"

urlpatterns = [
    path("inventory/", StockItemListView.as_view(), name="list"),
    path("inventory/new/", StockItemCreateView.as_view(), name="create"),
    path("inventory/matches/", StockMatchAPIView.as_view(), name="matches"),
    path("inventory/picker/", StockPickerAPIView.as_view(), name="picker"),
    path("stock/<uuid:reference>/", StockItemDetailView.as_view(), name="detail"),
    path("stock/<uuid:reference>/edit/", StockItemUpdateView.as_view(), name="edit"),
    path(
        "stock/<uuid:reference>/status/",
        StockItemStatusView.as_view(),
        name="status",
    ),
    path(
        "stock/<uuid:reference>/delete/",
        StockItemDeleteView.as_view(),
        name="delete",
    ),
    path(
        "stock/<uuid:reference>/adjust/",
        StockAdjustmentView.as_view(),
        name="adjust",
    ),
    path(
        "stock-documents/<uuid:reference>/attachment/",
        StockDocumentAttachmentView.as_view(),
        name="stock_document_attachment",
    ),
    path(
        "movements/<uuid:reference>/",
        StockMovementDetailView.as_view(),
        name="movement_detail",
    ),
    path(
        "movements/<uuid:reference>/attachment/",
        MovementAttachmentView.as_view(),
        name="movement_attachment",
    ),
    path(
        "movements/<uuid:reference>/reverse/",
        MovementReversalView.as_view(),
        name="movement_reverse",
    ),
    path("low-stock/", LowStockListView.as_view(), name="low_stock"),
    path("units/", UnitListCreateView.as_view(), name="units"),
    path("units/<int:pk>/edit/", UnitUpdateView.as_view(), name="unit_edit"),
    path("units/<int:pk>/status/", UnitStatusView.as_view(), name="unit_status"),
    path("units/<int:pk>/delete/", UnitDeleteView.as_view(), name="unit_delete"),
    path("suppliers/", SupplierListCreateView.as_view(), name="suppliers"),
    path("suppliers/<int:pk>/edit/", SupplierUpdateView.as_view(), name="supplier_edit"),
    path(
        "suppliers/<int:pk>/status/",
        SupplierStatusView.as_view(),
        name="supplier_status",
    ),
    path(
        "suppliers/<int:pk>/delete/",
        SupplierDeleteView.as_view(),
        name="supplier_delete",
    ),
]
