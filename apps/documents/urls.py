from django.urls import path

from . import api, views

app_name = "documents"

urlpatterns = [
    path("api/documents/", api.documents_api, name="documents-api"),
    path("api/documents/sources/", api.document_sources_api, name="document-sources-api"),
    path("api/documents/batch/settlement-statements/", api.batch_supplier_settlement_statements_api, name="batch-supplier-settlement-statements-api"),
    path("api/documents/batch/supplier-timesheets/", api.batch_supplier_timesheet_statements_api, name="batch-supplier-timesheet-statements-api"),
    path("api/documents/<uuid:document_id>/", api.document_detail_api, name="document-detail-api"),
    path("documents/<uuid:document_id>/print/", views.print_document, name="print-document"),
    path("documents/<uuid:document_id>/source-attachment/", views.document_source_attachment, name="document-source-attachment"),
    path("documents/<uuid:document_id>/brand/<str:kind>/", views.document_brand_asset, name="document-brand-asset"),
]
