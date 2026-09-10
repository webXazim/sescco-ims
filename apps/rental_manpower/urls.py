from django.urls import path

from . import api

app_name = "rental_manpower"

urlpatterns = [
    path("api/rental/settlements/", api.rental_settlements_api, name="settlements-api"),
    path("api/rental/settlements/calculate/", api.rental_settlements_calculate_api, name="settlements-calculate-api"),
    path("api/rental/settlements/workflow/", api.rental_settlements_workflow_api, name="settlements-workflow-api"),
    path("api/rental/adjustments/", api.rental_adjustments_api, name="adjustments-api"),
    path("api/rental/adjustments/<uuid:adjustment_id>/", api.rental_adjustment_detail_api, name="adjustment-detail-api"),
    path("api/rental/adjustments/<uuid:adjustment_id>/workflow/", api.rental_adjustment_workflow_api, name="adjustment-workflow-api"),
    path("api/rental/supplier-payments/", api.supplier_payments_api, name="supplier-payments-api"),
    path("api/rental/supplier-payments/<uuid:payment_id>/result/", api.supplier_payment_result_api, name="supplier-payment-result-api"),
    path("api/rental/supplier-payments/<uuid:payment_id>/retry/", api.supplier_payment_retry_api, name="supplier-payment-retry-api"),
    path("api/rental/timesheets/", api.rental_timesheets_api, name="timesheets-api"),
    path("api/rental/timesheets/overtime/", api.rental_timesheet_overtime_api, name="timesheets-overtime-api"),
    path("api/rental/timesheets/workflow/", api.rental_timesheet_workflow_api, name="timesheets-workflow-api"),
    path("api/rental/assignments/", api.assignments_api, name="assignments-api"),
    path("api/rental/suppliers/", api.suppliers_api, name="suppliers-api"),
    path("api/rental/suppliers/<uuid:supplier_id>/", api.supplier_detail_api, name="supplier-detail-api"),
    path("api/rental/projects/", api.projects_api, name="projects-api"),
    path("api/rental/projects/<uuid:project_id>/", api.project_detail_api, name="project-detail-api"),
    path("api/rental/workers/", api.workers_api, name="workers-api"),
    path("api/rental/workers/import/", api.workers_import_api, name="workers-import-api"),
    path("api/rental/workers/<uuid:worker_id>/", api.worker_detail_api, name="worker-detail-api"),
]
