from django.urls import path

from . import api, views

app_name = "documents"

urlpatterns = [
    path("api/documents/", api.documents_api, name="documents-api"),
    path("api/documents/sources/", api.document_sources_api, name="document-sources-api"),
    path("api/documents/generator/types/", api.document_generator_types_api, name="document-generator-types-api"),
    path("api/documents/generator/suppliers/", api.document_generator_suppliers_api, name="document-generator-suppliers-api"),
    path("api/documents/generator/projects/", api.document_generator_projects_api, name="document-generator-projects-api"),
    path("api/documents/generator/sources/", api.document_generator_sources_api, name="document-generator-sources-api"),
    path("api/documents/generator/review/", api.document_generator_review_api, name="document-generator-review-api"),
    path("api/documents/generator/create/", api.document_generator_create_api, name="document-generator-create-api"),
    path("api/documents/generation-options/", api.document_generation_options_api, name="document-generation-options-api"),
    path("api/documents/generation-plan/", api.document_generation_plan_api, name="document-generation-plan-api"),
    path("api/documents/generate/", api.document_generation_execute_api, name="document-generation-execute-api"),
    path("api/documents/generation-batches/", api.document_generation_batches_api, name="document-generation-batches-api"),
    path("api/documents/<uuid:document_id>/delivery-options/", api.document_delivery_options_api, name="document-delivery-options-api"),
    path("api/documents/delivery-center/", api.document_delivery_center_api, name="document-delivery-center-api"),
    path("api/documents/delivery-operations/", api.document_delivery_operations_api, name="document-delivery-operations-api"),
    path("api/documents/delivery-batches/", api.document_delivery_batch_prepare_api, name="document-delivery-batch-prepare-api"),
    path("api/documents/delivery-batches/<uuid:batch_event_id>/dispatch/", api.document_delivery_batch_dispatch_api, name="document-delivery-batch-dispatch-api"),
    path("api/documents/delivery-packs/", api.document_delivery_pack_api, name="document-delivery-pack-api"),
    path("api/documents/delivery-packs/<uuid:pack_event_id>/dispatch/", api.document_delivery_dispatch_api, name="document-delivery-dispatch-api"),
    path("api/documents/delivery-packs/<uuid:pack_event_id>/sent/", api.document_delivery_confirm_sent_api, name="document-delivery-confirm-sent-api"),
    path("api/documents/delivery-packs/<uuid:pack_event_id>/share/revoke/", api.document_delivery_share_revoke_api, name="document-delivery-share-revoke-api"),
    path("api/documents/delivery-packs/<uuid:pack_event_id>/share/reissue/", api.document_delivery_share_reissue_api, name="document-delivery-share-reissue-api"),
    path("api/documents/delivery-packs/<uuid:pack_event_id>/delivered/", api.document_delivery_mark_delivered_api, name="document-delivery-mark-delivered-api"),
    path("api/documents/batch/settlement-statements/", api.batch_supplier_settlement_statements_api, name="batch-supplier-settlement-statements-api"),
    path("api/documents/batch/supplier-timesheets/", api.batch_supplier_timesheet_statements_api, name="batch-supplier-timesheet-statements-api"),
    path("api/documents/<uuid:document_id>/", api.document_detail_api, name="document-detail-api"),
    path("documents/delivery-packs/<uuid:pack_event_id>/share/<str:token>/", views.delivery_pack_share, name="delivery-pack-share"),
    path("documents/delivery-packs/<uuid:pack_event_id>/share/<str:token>/acknowledge/", views.delivery_pack_share_acknowledge, name="delivery-pack-share-acknowledge"),
    path("documents/delivery-packs/<uuid:pack_event_id>/share/<str:token>/documents/<uuid:document_id>/print/", views.delivery_pack_shared_document_print, name="delivery-pack-shared-document-print"),
    path("documents/delivery-packs/<uuid:pack_event_id>/share/<str:token>/documents/<uuid:document_id>/workers/<uuid:worker_id>/print/", views.delivery_pack_shared_worker_print, name="delivery-pack-shared-worker-print"),
    path("documents/delivery-packs/<uuid:pack_event_id>/print/", views.print_delivery_pack, name="print-delivery-pack"),
    path("documents/<uuid:document_id>/print/", views.print_document, name="print-document"),
    path("documents/<uuid:document_id>/workers/<uuid:worker_id>/print/", views.print_supplier_timesheet_worker, name="print-supplier-timesheet-worker"),
    path("documents/<uuid:document_id>/source-attachment/", views.document_source_attachment, name="document-source-attachment"),
    path("documents/<uuid:document_id>/brand/<str:kind>/", views.document_brand_asset, name="document-brand-asset"),
]
