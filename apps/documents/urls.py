from django.urls import path

from . import api, views

app_name = "documents"

urlpatterns = [
    path("api/documents/", api.documents_api, name="documents-api"),
    path("api/documents/sources/", api.document_sources_api, name="document-sources-api"),
    path("api/documents/<uuid:document_id>/", api.document_detail_api, name="document-detail-api"),
    path("documents/<uuid:document_id>/print/", views.print_document, name="print-document"),
    path("documents/<uuid:document_id>/asset/<str:asset_kind>/", views.print_document_asset, name="document-asset"),
]
