from __future__ import annotations

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from apps.core.access import InventoryAdminRequiredMixin, InventoryWorkspaceMixin
from apps.inventory.selectors import stock_items
from apps.projects.models import Project

from .forms import (
    ImportConfirmForm,
    LegacyImportUploadForm,
    OpeningStockImportUploadForm,
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


class FilteredExportView(InventoryWorkspaceMixin, View):
    dataset_name = ""

    def get(self, request, file_format):
        try:
            if self.dataset_name == "inventory":
                dataset = inventory_dataset(request.GET)
            elif self.dataset_name == "low-stock":
                dataset = inventory_dataset(request.GET, low_stock=True)
            elif self.dataset_name == "activity":
                dataset = activity_dataset(request.GET)
            else:
                raise Http404("Unsupported export dataset.")
            return export_response(
                dataset=dataset,
                user=request.user,
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


class StockHistoryExportView(InventoryWorkspaceMixin, View):
    def get(self, request, reference, file_format):
        stock_item = get_object_or_404(stock_items(), reference=reference)
        try:
            dataset = stock_history_dataset(stock_item, request.GET)
            return export_response(
                dataset=dataset,
                user=request.user,
                file_format=file_format,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("inventory:detail", reference=stock_item.reference)


class ProjectInventoryExportView(InventoryWorkspaceMixin, View):
    def get(self, request, code, file_format):
        project = get_object_or_404(Project, code=code)
        try:
            dataset = project_inventory_dataset(project, request.GET)
            return export_response(
                dataset=dataset,
                user=request.user,
                file_format=file_format,
            )
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect("projects:detail", code=project.code)


class ImportJobListView(InventoryAdminRequiredMixin, ListView):
    model = ImportJob
    template_name = "data_exchange/import_job_list.html"
    context_object_name = "import_jobs"
    paginate_by = 30

    def get_queryset(self):
        queryset = ImportJob.objects.select_related(
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


class LegacyImportCreateView(InventoryAdminRequiredMixin, View):
    template_name = "data_exchange/import_upload.html"

    def get(self, request):
        return render(request, self.template_name, self._context(LegacyImportUploadForm()))

    def post(self, request):
        form = LegacyImportUploadForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data["source_file"]
            job = ImportJob.objects.create(
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


class OpeningImportCreateView(InventoryAdminRequiredMixin, View):
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


class ImportJobDetailView(InventoryAdminRequiredMixin, View):
    template_name = "data_exchange/import_job_detail.html"

    def get_job(self, reference):
        return get_object_or_404(
            ImportJob.objects.select_related(
                "project",
                "default_unit",
                "created_by",
            ),
            reference=reference,
        )

    def get(self, request, reference):
        job = self.get_job(reference)
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


class ImportJobConfirmView(InventoryAdminRequiredMixin, View):
    def post(self, request, reference):
        job = get_object_or_404(ImportJob, reference=reference)
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


class OpeningTemplateView(InventoryAdminRequiredMixin, View):
    def get(self, request):
        return opening_stock_template_response(user=request.user)


class ImportSourceFileView(InventoryAdminRequiredMixin, View):
    def get(self, request, reference):
        job = get_object_or_404(ImportJob, reference=reference)
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
