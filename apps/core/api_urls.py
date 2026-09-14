from django.urls import path

from . import management_api, record_management_api, settings_api

app_name = "platform_api"

urlpatterns = [
    path("api/settings/", settings_api.company_settings_api, name="company-settings-api"),
    path("api/settings/branding/<str:kind>/", settings_api.company_branding_asset_api, name="company-branding-asset"),
    path("api/management/", management_api.management_api, name="management-api"),
    path("api/management/summary/", management_api.management_summary_api, name="management-summary-api"),
    path("api/management/approvals/", management_api.management_approvals_api, name="management-approvals-api"),
    path("api/management/audit/", management_api.management_audit_api, name="management-audit-api"),
    path("api/reports/", management_api.reports_api, name="reports-api"),
    path("api/record-management/", record_management_api.record_management_api, name="record-management-api"),
    path("api/reports/export.csv", management_api.report_export_api, name="reports-export-api"),
]
