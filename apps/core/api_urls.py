from django.urls import path

from . import management_api, settings_api

app_name = "platform_api"

urlpatterns = [
    path("api/settings/", settings_api.company_settings_api, name="company-settings-api"),
    path("api/settings/document-assets/<str:asset_kind>/", settings_api.company_document_asset_api, name="company-document-asset-api"),
    path("api/settings/document-assets/<str:asset_kind>/file/", settings_api.company_document_asset_file, name="company-document-asset-file"),
    path("api/management/", management_api.management_api, name="management-api"),
    path("api/reports/", management_api.reports_api, name="reports-api"),
    path("api/reports/export.csv", management_api.report_export_api, name="reports-export-api"),
]
