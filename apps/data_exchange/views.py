from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.core.access import InventoryPermissionRequiredMixin
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.inventory.access import (
    restrict_inventory_location_queryset,
    restrict_inventory_projects,
    restrict_inventory_stock,
)
from apps.inventory.models import InventoryLocation
from apps.inventory.selectors import stock_items
from apps.inventory.services.stock import InventoryOperationError
from apps.inventory.services.transfers import transfer_stock
from apps.projects.models import Project

from .forms import (
    ImportConfirmForm,
    LegacyImportUploadForm,
    OpeningStockImportUploadForm,
    TransferWorkbookUploadForm,
)
from .models import ImportJob
from .opening_schema import OPENING_IMPORT_COLUMNS, OPENING_IMPORT_RULES
from .services.exporting import (
    activity_dataset,
    export_response,
    inventory_dataset,
    opening_stock_template_response,
    project_inventory_dataset,
    stock_history_dataset,
)
from .services.importing import (
    ImportPreviewError,
    ImportProcessingError,
    confirm_import,
    preview_import,
)
from .services.transfer_workbooks import (
    TransferWorkbookError,
    parse_transfer_workbook,
    transfer_workbook_response,
)


class FilteredExportView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_EXPORT_EXECUTE
    dataset_name = ""

    def get(self, request, file_format):
        try:
            if self.dataset_name == "inventory":
                dataset = inventory_dataset(request.GET, company=request.company, membership=request.company_membership)
            elif self.dataset_name == "low-stock":
                dataset = inventory_dataset(request.GET, company=request.company, membership=request.company_membership, low_stock=True)
            elif self.dataset_name == "activity":
                dataset = activity_dataset(request.GET, company=request.company, membership=request.company_membership)
            else:
                raise Http404("Unsupported export dataset.")
            return export_response(
                dataset=dataset,
                user=request.user,
                company=request.company,
                file_format=file_format,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            fallback = {
                "inventory": "inventory:list",
                "low-stock": "inventory:low_stock",
                "activity": "core:activity",
            }[self.dataset_name]
            return redirect(fallback)


class InventoryExportView(FilteredExportView):
    dataset_name = "inventory"


class LowStockExportView(FilteredExportView):
    dataset_name = "low-stock"


class ActivityExportView(FilteredExportView):
    dataset_name = "activity"


class StockHistoryExportView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_EXPORT_EXECUTE
    def get(self, request, reference, file_format):
        stock_item = get_object_or_404(restrict_inventory_stock(stock_items(request.company), request.company_membership), reference=reference)
        try:
            dataset = stock_history_dataset(stock_item, request.GET)
            return export_response(
                dataset=dataset,
                user=request.user,
                company=request.company,
                file_format=file_format,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:detail", reference=stock_item.reference)


class ProjectInventoryExportView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_EXPORT_EXECUTE
    def get(self, request, code, file_format):
        project = get_object_or_404(restrict_inventory_projects(Project.objects.for_company(request.company), request.company_membership), code=code)
        try:
            dataset = project_inventory_dataset(project, request.GET)
            return export_response(
                dataset=dataset,
                user=request.user,
                company=request.company,
                file_format=file_format,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("projects:detail", code=project.code)


def _active_transfer_locations(request):
    return restrict_inventory_location_queryset(
        InventoryLocation.objects.for_company(request.company).select_related("project"),
        request.company_membership,
    ).filter(
        Q(
            location_type=InventoryLocation.Type.OFFICE,
            is_active=True,
            archived_at__isnull=True,
            deleted_at__isnull=True,
        )
        | Q(
            location_type=InventoryLocation.Type.PROJECT,
            is_active=True,
            archived_at__isnull=True,
            deleted_at__isnull=True,
            project__status=Project.Status.ACTIVE,
            project__deleted_at__isnull=True,
        )
    )


class TransferWorkbookExportView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_EXPORT_EXECUTE

    def get(self, request, location_id):
        source = get_object_or_404(_active_transfer_locations(request), pk=location_id)
        try:
            return transfer_workbook_response(source_location=source, user=request.user)
        except TransferWorkbookError as exc:
            messages.error(request, str(exc))
            return redirect("data_exchange:transfer_workbook", location_id=source.pk)


class TransferWorkbookImportView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_STOCK_TRANSFER
    template_name = "data_exchange/transfer_workbook.html"

    def test_func(self):
        return bool(
            super().test_func()
            and membership_has_permission(
                getattr(self.request, "company_membership", None),
                AccessPermission.INVENTORY_IMPORT_EXECUTE,
            )
        )

    def _source(self, request, location_id):
        return get_object_or_404(_active_transfer_locations(request), pk=location_id)

    def _form(self, request, source, *, data=None, files=None):
        return TransferWorkbookUploadForm(
            data,
            files,
            company=request.company,
            membership=request.company_membership,
            source_location=source,
        )

    def _context(self, source, form):
        return {
            "page_key": "transfers",
            "page_title": "Transfer stock with Excel",
            "page_subtitle": (
                "Export this location's current balances, enter transfer quantities, "
                "then upload the worksheet to a project or office."
            ),
            "source": source,
            "form": form,
        }

    def get(self, request, location_id):
        source = self._source(request, location_id)
        return render(request, self.template_name, self._context(source, self._form(request, source)))

    def post(self, request, location_id):
        source = self._source(request, location_id)
        form = self._form(request, source, data=request.POST, files=request.FILES)
        if form.is_valid():
            try:
                with transaction.atomic():
                    parsed = parse_transfer_workbook(
                        source_file=form.cleaned_data["source_file"],
                        company=request.company,
                        source_location=source,
                    )
                    destination = form.cleaned_data["destination_location"]
                    result = transfer_stock(
                        user=request.user,
                        idempotency_key=parsed.manifest_id,
                        source_location=source,
                        destination_location=destination,
                        transfer_date=form.cleaned_data["transfer_date"],
                        allocations=list(parsed.allocations),
                        document_reference=form.cleaned_data["document_reference"],
                        notes=form.cleaned_data["notes"],
                    )
                    target = result.approval_request or result.transfer
                    if target is None:
                        raise InventoryOperationError("The Excel transfer did not create a result.")
                    if not result.duplicate_submission:
                        record_audit_event(
                            company=request.company,
                            area=AuditArea.INVENTORY,
                            action="inventory.transfer_workbook.imported",
                            object_type=(
                                "inventory.StockApprovalRequest"
                                if result.approval_request
                                else "inventory.StockTransfer"
                            ),
                            object_id=target.reference,
                            object_label=str(target),
                            actor_membership=request.company_membership,
                            after={
                                "source_location_id": source.pk,
                                "destination_location_id": destination.pk,
                                "selected_rows": parsed.selected_rows,
                                "status": getattr(target, "status", "completed"),
                            },
                            metadata={"manifest_id": str(parsed.manifest_id)},
                            request=request,
                        )
            except (TransferWorkbookError, InventoryOperationError, ValueError) as exc:
                form.add_error("source_file", str(exc))
            else:
                if result.duplicate_submission:
                    messages.info(request, "This Excel worksheet was already imported; the original result is shown.")
                elif result.approval_request:
                    messages.success(
                        request,
                        "Excel transfer submitted for destination-project approval. No balances changed yet.",
                    )
                else:
                    messages.success(request, "Excel transfer posted successfully.")
                if result.approval_request:
                    return redirect(
                        "inventory:approval_detail",
                        reference=result.approval_request.reference,
                    )
                return redirect("inventory:transfer_detail", reference=result.transfer.reference)
        return render(request, self.template_name, self._context(source, form), status=400)


class ImportJobListView(InventoryPermissionRequiredMixin, ListView):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    model = ImportJob
    template_name = "data_exchange/import_job_list.html"
    context_object_name = "import_jobs"
    paginate_by = 30

    def get_queryset(self):
        queryset = ImportJob.objects.for_company(self.request.company).select_related(
            "project",
            "default_unit",
            "created_by",
        )
        query = self.request.GET.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(original_filename__icontains=query)
                | Q(project__code__icontains=query)
                | Q(project__name__icontains=query)
                | Q(created_by__username__icontains=query)
                | Q(status__icontains=query)
                | Q(import_type__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="imports",
            page_title="Excel imports",
            page_subtitle=(
                "Preview every workbook row before creating records or opening stock."
            ),
            search_query=self.request.GET.get("q", ""),
        )
        return context


class LegacyImportCreateView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    template_name = "data_exchange/import_upload.html"

    def get(self, request):
        return render(request, self.template_name, self._context(LegacyImportUploadForm(company=request.company, membership=request.company_membership)))

    def post(self, request):
        form = LegacyImportUploadForm(request.POST, request.FILES, company=request.company, membership=request.company_membership)
        if form.is_valid():
            file = form.cleaned_data["source_file"]
            job = ImportJob.objects.create(
                company=request.company,
                import_type=ImportJob.Type.LEGACY_CATALOG,
                source_file=file,
                original_filename=file.name,
                project=form.cleaned_data["project"],
                default_unit=form.cleaned_data["default_unit"],
                options={
                    "update_existing_records": form.cleaned_data[
                        "update_existing_records"
                    ]
                },
                created_by=request.user,
            )
            try:
                preview_import(job)
            except ImportPreviewError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Workbook parsed. Review the preview before import.")
            return redirect("data_exchange:import_detail", reference=job.reference)
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "imports",
            "page_title": "Import existing Excel database",
            "page_subtitle": (
                "Import the current Database sheet without changing stock quantities."
            ),
            "form": form,
            "submit_label": "Build preview",
            "import_kind": "legacy",
        }


class OpeningImportCreateView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    template_name = "data_exchange/import_upload.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            self._context(OpeningStockImportUploadForm()),
        )

    def post(self, request):
        form = OpeningStockImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data["source_file"]
            job = ImportJob.objects.create(
                company=request.company,
                import_type=ImportJob.Type.OPENING_STOCK,
                source_file=file,
                original_filename=file.name,
                created_by=request.user,
            )
            try:
                preview_import(job)
            except ImportPreviewError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Opening stock parsed. Review every row before import.")
            return redirect("data_exchange:import_detail", reference=job.reference)
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "imports",
            "page_title": "Import opening stock",
            "page_subtitle": (
                "Create first balances through proper immutable opening movements."
            ),
            "form": form,
            "submit_label": "Build preview",
            "import_kind": "opening",
            "opening_columns": OPENING_IMPORT_COLUMNS,
            "opening_rules": OPENING_IMPORT_RULES,
        }


class ImportJobDetailView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    template_name = "data_exchange/import_job_detail.html"

    def get_job(self, request, reference):
        return get_object_or_404(
            ImportJob.objects.for_company(request.company).select_related(
                "project",
                "default_unit",
                "created_by",
            ),
            reference=reference,
        )

    def get(self, request, reference):
        job = self.get_job(request, reference)
        rows = job.rows.select_related(
            "exact_match",
            "imported_stock_item",
            "movement",
        )
        paginator = Paginator(rows, 100)
        row_page = paginator.get_page(request.GET.get("page"))
        return render(
            request,
            self.template_name,
            {
                "page_key": "imports",
                "page_title": "Import preview",
                "page_subtitle": job.original_filename,
                "job": job,
                "rows": row_page.object_list,
                "page_obj": row_page,
                "paginator": paginator,
                "is_paginated": row_page.has_other_pages(),
                "confirm_form": ImportConfirmForm(),
            },
        )


class ImportJobConfirmView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    def post(self, request, reference):
        job = get_object_or_404(ImportJob.objects.for_company(request.company), reference=reference)
        form = ImportConfirmForm(request.POST)
        if not form.is_valid():
            messages.error(request, "Confirm that you reviewed the import preview.")
            return redirect("data_exchange:import_detail", reference=job.reference)
        try:
            result = confirm_import(
                job=job,
                user=request.user,
                include_similar_rows=form.cleaned_data["include_similar_rows"],
            )
        except ImportProcessingError as exc:
            messages.error(request, f"Nothing was partially imported. {exc}")
        else:
            messages.success(
                request,
                f"Import completed: {result.imported_rows} imported, "
                f"{result.skipped_rows} skipped.",
            )
        return redirect("data_exchange:import_detail", reference=job.reference)


class OpeningTemplateView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    def get(self, request):
        return opening_stock_template_response(user=request.user, company=request.company)


class ImportSourceFileView(InventoryPermissionRequiredMixin, View):
    inventory_permission = AccessPermission.INVENTORY_IMPORT_EXECUTE
    def get(self, request, reference):
        job = get_object_or_404(ImportJob.objects.for_company(request.company), reference=reference)
        if not job.source_file:
            raise Http404("Import source file not found.")
        try:
            handle = job.source_file.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Import source file not found.") from exc
        from django.http import FileResponse

        response = FileResponse(
            handle,
            as_attachment=True,
            filename=job.original_filename,
        )
        response["Cache-Control"] = "private, no-store"
        return response
