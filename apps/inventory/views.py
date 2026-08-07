from __future__ import annotations

from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, ListView, UpdateView

from apps.core.access import InventoryAdminRequiredMixin, InventoryWorkspaceMixin
from apps.explorer.filtering import resolve_date_range
from apps.explorer.forms import SavedViewCreateForm
from apps.explorer.models import SavedView
from apps.projects.models import Project
from apps.projects.selectors import active_projects

from .forms import (
    MovementFilterForm,
    StockHistoryFilterForm,
    StockItemFilterForm,
    MovementReversalForm,
    StockAdditionForm,
    StockAdjustmentForm,
    StockItemForm,
    StockUsageForm,
    SupplierForm,
    UnitForm,
)
from .models import StockItem, StockMovement, Supplier, Unit
from .selectors import (
    apply_movement_search,
    apply_stock_search,
    filter_stock_items,
    filter_stock_movements,
    low_stock_items,
    stock_items,
    stock_movements,
)
from .services.matching import find_stock_matches
from .services.stock import (
    InventoryOperationError,
    add_stock,
    adjust_stock,
    reverse_movement,
    set_stock_item_status,
    use_stock,
)



DEFAULT_STOCK_COLUMNS = (
    "project", "material", "supplier", "phone", "quantity", "minimum", "unit",
    "price", "latest_addition", "stock_status", "updated",
)
DEFAULT_MOVEMENT_COLUMNS = (
    "date", "project", "material", "type", "quantity", "balance", "reference", "user",
)
STOCK_SORTS = {
    "project": ("project__code", "material_name", "supplier_name"),
    "material": ("material_name", "supplier_name"),
    "-material": ("-material_name", "supplier_name"),
    "supplier": ("supplier_name", "material_name"),
    "-supplier": ("-supplier_name", "material_name"),
    "quantity": ("current_quantity", "material_name"),
    "-quantity": ("-current_quantity", "material_name"),
    "minimum": ("minimum_quantity", "material_name"),
    "-minimum": ("-minimum_quantity", "material_name"),
    "updated": ("-updated_at", "material_name"),
    "created": ("-created_at", "material_name"),
    "latest-addition": (F("latest_addition_date").desc(nulls_last=True), "material_name"),
    "oldest-addition": (F("latest_addition_date").asc(nulls_last=True), "material_name"),
    "price": (F("latest_unit_price").asc(nulls_last=True), "material_name"),
    "-price": (F("latest_unit_price").desc(nulls_last=True), "material_name"),
}
MOVEMENT_SORTS = {
    "-date": ("-movement_date", "-created_at", "-pk"),
    "date": ("movement_date", "created_at", "pk"),
    "project": ("project_code_snapshot", "material_name_snapshot", "-movement_date"),
    "material": ("material_name_snapshot", "-movement_date"),
    "type": ("movement_type", "-movement_date"),
    "quantity": ("quantity", "-movement_date"),
    "-quantity": ("-quantity", "-movement_date"),
    "user": ("created_by__first_name", "created_by__username", "-movement_date"),
}

def _bound_filter_data(request, defaults: dict[str, object]):
    data = request.GET.copy()
    for key, value in defaults.items():
        if key in data:
            continue
        if isinstance(value, (tuple, list)):
            data.setlist(key, [str(item) for item in value])
        else:
            data[key] = str(value)
    return data

def _query_url_without(request, *keys: str) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("movement_page", None)
    for key in keys:
        query.pop(key, None)
    encoded = query.urlencode()
    return f"{request.path}?{encoded}" if encoded else request.path

def _chip(label: str, request, *keys: str) -> dict[str, str]:
    return {"label": label, "clear_url": _query_url_without(request, *keys)}

def _stock_filter_chips(request, data: dict) -> list[dict[str, str]]:
    chips = []
    if data.get("q"):
        chips.append(_chip(f'Search: {data["q"]}', request, "q"))
    if data.get("project"):
        project = data["project"]
        chips.append(_chip(f"Project: {project.code}", request, "project"))
    if data.get("project_status"):
        status_label = dict(Project.Status.choices)[data["project_status"]]
        chips.append(
            _chip(
                f"Project status: {status_label}",
                request,
                "project_status",
            )
        )

    text_fields = (
        ("material", "Material"),
        ("description", "Description"),
        ("supplier", "Supplier"),
        ("supplier_phone", "Phone"),
        ("supplier_location", "Location"),
    )
    for key, label in text_fields:
        if data.get(key):
            chips.append(_chip(f"{label}: {data[key]}", request, key))

    if data.get("unit"):
        names = ", ".join(unit.symbol for unit in data["unit"])
        chips.append(_chip(f"Unit: {names}", request, "unit"))
    if data.get("stock_status"):
        labels = dict(StockItemFilterForm.STOCK_STATUS_CHOICES)
        chips.append(_chip(labels[data["stock_status"]], request, "stock_status"))
    if data.get("status") and data["status"] != StockItem.Status.ACTIVE:
        labels = dict(StockItemFilterForm.RECORD_STATUS_CHOICES)
        chips.append(_chip(labels[data["status"]], request, "status"))

    range_fields = (
        ("quantity_min", "quantity_max", "Quantity"),
        ("minimum_min", "minimum_max", "Minimum"),
        ("price_min", "price_max", "Price"),
    )
    for lower, upper, label in range_fields:
        if data.get(lower) is None and data.get(upper) is None:
            continue
        if data.get(lower) is not None and data.get(upper) is not None:
            value = f"{data[lower]} – {data[upper]}"
        elif data.get(lower) is not None:
            value = f"≥ {data[lower]}"
        else:
            value = f"≤ {data[upper]}"
        chips.append(_chip(f"{label}: {value}", request, lower, upper))

    date_range = resolve_date_range(
        data.get("date_preset") or "",
        start=data.get("date_from"),
        end=data.get("date_to"),
    )
    if date_range.start or date_range.end:
        date_field = data.get("date_field") or "latest_addition_date"
        field_label = dict(StockItemFilterForm.DATE_FIELD_CHOICES).get(
            date_field,
            "Date",
        )
        chips.append(
            _chip(
                f"{field_label}: {date_range.label}",
                request,
                "date_preset",
                "date_from",
                "date_to",
            )
        )
    if data.get("created_by"):
        chips.append(
            _chip(
                f"Created by: {data['created_by'].display_name}",
                request,
                "created_by",
            )
        )
    if data.get("updated_by"):
        chips.append(
            _chip(
                f"Updated by: {data['updated_by'].display_name}",
                request,
                "updated_by",
            )
        )
    return chips


def _movement_filter_chips(request, data: dict) -> list[dict[str, str]]:
    chips = []
    if data.get("q"):
        chips.append(_chip(f'Search: {data["q"]}', request, "q"))
    if data.get("project"):
        project_names = ", ".join(project.code for project in data["project"])
        chips.append(_chip(f"Project: {project_names}", request, "project"))
    if data.get("project_status"):
        status_label = dict(Project.Status.choices)[data["project_status"]]
        chips.append(
            _chip(
                f"Project status: {status_label}",
                request,
                "project_status",
            )
        )

    text_fields = (
        ("material", "Material"),
        ("supplier", "Supplier"),
        ("supplier_phone", "Phone"),
        ("reference", "Reference"),
        ("purpose", "Purpose"),
        ("recipient", "Recipient"),
        ("reason", "Reason"),
    )
    for key, label in text_fields:
        if data.get(key):
            chips.append(_chip(f"{label}: {data[key]}", request, key))

    if data.get("movement_type"):
        labels = dict(StockMovement.Type.choices)
        values = ", ".join(labels[value] for value in data["movement_type"])
        chips.append(_chip(f"Action: {values}", request, "movement_type"))

    range_fields = (
        ("quantity_min", "quantity_max", "Quantity"),
        ("price_min", "price_max", "Price"),
    )
    for lower, upper, label in range_fields:
        if data.get(lower) is None and data.get(upper) is None:
            continue
        if data.get(lower) is not None and data.get(upper) is not None:
            value = f"{data[lower]} – {data[upper]}"
        elif data.get(lower) is not None:
            value = f"≥ {data[lower]}"
        else:
            value = f"≤ {data[upper]}"
        chips.append(_chip(f"{label}: {value}", request, lower, upper))

    date_range = resolve_date_range(
        data.get("date_preset") or "",
        start=data.get("date_from"),
        end=data.get("date_to"),
    )
    if date_range.start or date_range.end:
        chips.append(
            _chip(
                f"Activity date: {date_range.label}",
                request,
                "date_preset",
                "date_from",
                "date_to",
            )
        )
    if data.get("created_by"):
        chips.append(
            _chip(
                f"User: {data['created_by'].display_name}",
                request,
                "created_by",
            )
        )
    return chips


def _source_query(request) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("movement_page", None)
    return query.urlencode()

def _operation_error_message(exc: ValidationError) -> str:
    return exc.messages[0] if exc.messages else "The inventory operation could not be completed."


def _stock_item_from_reference(value: str) -> StockItem | None:
    if not value:
        return None
    try:
        return stock_items().filter(reference=value).first()
    except (ValidationError, ValueError):
        return None


class StockItemListView(InventoryWorkspaceMixin, ListView):
    model = StockItem
    template_name = "inventory/stockitem_list.html"
    context_object_name = "stock_items"
    paginate_by = 50
    view_type = SavedView.ViewType.INVENTORY

    def get_filter_form(self):
        data = _bound_filter_data(
            self.request,
            {
                "status": StockItem.Status.ACTIVE,
                "date_field": "latest_addition_date",
                "sort": "project",
                "columns": DEFAULT_STOCK_COLUMNS,
            },
        )
        return StockItemFilterForm(data)

    def get_queryset(self):
        self.filter_form = self.get_filter_form()
        queryset = stock_items()
        if self.filter_form.is_valid():
            self.filter_data = self.filter_form.cleaned_data
            queryset = filter_stock_items(queryset, self.filter_data)
            sort = self.filter_data.get("sort") or "project"
            return queryset.order_by(*STOCK_SORTS.get(sort, STOCK_SORTS["project"]))
        self.filter_data = {}
        return queryset.none()

    def get_visible_columns(self):
        requested = self.request.GET.getlist("columns")
        allowed = {value for value, _ in StockItemFilterForm.COLUMN_CHOICES}
        selected = [value for value in requested if value in allowed]
        return tuple(selected) if selected else DEFAULT_STOCK_COLUMNS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = self.filter_data
        context.update(
            page_key="inventory",
            page_title="Inventory Explorer",
            page_subtitle="Search and filter every project stock field from one workspace.",
            filter_form=self.filter_form,
            filter_chips=_stock_filter_chips(self.request, data) if data else [],
            visible_columns=self.get_visible_columns(),
            current_sort=data.get("sort") or "project",
            advanced_open=not self.filter_form.is_valid(),
            custom_date_open=data.get("date_preset") == "custom",
            clear_url=reverse("inventory:list"),
            saved_view_form=SavedViewCreateForm(),
            saved_view_type=self.view_type,
            source_query=_source_query(self.request),
            sort_choices=StockItemFilterForm.SORT_CHOICES,
            default_columns=DEFAULT_STOCK_COLUMNS,
        )
        return context


class StockItemCreateView(InventoryWorkspaceMixin, View):
    """Preserve the old URL while enforcing creation through an addition movement."""

    def get(self, request):
        target = reverse("core:add_stock")
        project_code = request.GET.get("project", "").strip()
        if project_code and active_projects().filter(code=project_code).exists():
            target = f"{target}?{urlencode({'project': project_code})}"
        return redirect(target)

    def post(self, request):
        return self.get(request)


class StockItemUpdateView(InventoryWorkspaceMixin, UpdateView):
    model = StockItem
    form_class = StockItemForm
    template_name = "inventory/stockitem_form.html"
    slug_field = "reference"
    slug_url_kwarg = "reference"

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        try:
            with transaction.atomic():
                response = super().form_valid(form)
        except IntegrityError:
            form.add_error(
                None,
                "Those identity fields now match another stock record. "
                "Review the project, material, supplier, and phone.",
            )
            return self.form_invalid(form)
        messages.success(self.request, "Stock record information was updated.")
        return response

    def get_success_url(self):
        return reverse("inventory:detail", kwargs={"reference": self.object.reference})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="stock-detail",
            page_title="Edit stock record",
            page_subtitle="Identity changes are checked against existing project stock.",
            submit_label="Save changes",
            similar_matches=getattr(context["form"], "similar_matches", []),
            exact_match=getattr(context["form"], "exact_match", None),
        )
        return context


class StockItemStatusView(InventoryWorkspaceMixin, View):
    def post(self, request, reference):
        stock_item = get_object_or_404(stock_items(), reference=reference)
        action = request.POST.get("action", "").strip()
        target_status = {
            "archive": StockItem.Status.ARCHIVED,
            "reactivate": StockItem.Status.ACTIVE,
        }.get(action)
        if not target_status:
            messages.error(request, "Choose a valid stock-record action.")
            return redirect("inventory:detail", reference=stock_item.reference)
        try:
            updated = set_stock_item_status(
                stock_item=stock_item, user=request.user, status=target_status
            )
        except InventoryOperationError as exc:
            messages.error(request, _operation_error_message(exc))
        else:
            verb = "reactivated" if updated.status == StockItem.Status.ACTIVE else "archived"
            messages.success(request, f"Stock record was {verb}.")
        return redirect("inventory:detail", reference=stock_item.reference)


class StockItemDetailView(InventoryWorkspaceMixin, DetailView):
    model = StockItem
    template_name = "inventory/stockitem_detail.html"
    context_object_name = "stock_item"
    slug_field = "reference"
    slug_url_kwarg = "reference"

    def get_queryset(self):
        return stock_items()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = _bound_filter_data(self.request, {"sort": "-date"})
        history_form = StockHistoryFilterForm(data)
        movements = stock_movements().filter(stock_item=self.object)
        history_data = {}
        if history_form.is_valid():
            history_data = history_form.cleaned_data
            movements = apply_movement_search(movements, history_data.get("q") or "")
            if history_data.get("movement_type"):
                movements = movements.filter(movement_type__in=history_data["movement_type"])
            if history_data.get("created_by"):
                movements = movements.filter(created_by=history_data["created_by"])
            date_range = resolve_date_range(
                history_data.get("date_preset") or "",
                start=history_data.get("date_from"),
                end=history_data.get("date_to"),
            )
            if date_range.start:
                movements = movements.filter(movement_date__gte=date_range.start)
            if date_range.end:
                movements = movements.filter(movement_date__lte=date_range.end)
            movement_sort = history_data.get("sort") or "-date"
            movements = movements.order_by(
                *MOVEMENT_SORTS.get(movement_sort, MOVEMENT_SORTS["-date"])
            )
        else:
            movements = movements.none()
        paginator = Paginator(movements, 25)
        movement_page = paginator.get_page(self.request.GET.get("movement_page"))
        context.update(
            page_key="stock-detail",
            page_title="Stock details",
            page_subtitle="Current balance and filterable immutable movement history.",
            movement_page=movement_page,
            movement_count=movements.count(),
            total_movement_count=stock_movements().filter(stock_item=self.object).count(),
            history_form=history_form,
            history_chips=(
                _movement_filter_chips(self.request, history_data)
                if history_data
                else []
            ),
            history_advanced_open=(
                bool(set(self.request.GET.keys()) - {"movement_page"})
                or not history_form.is_valid()
            ),
            can_archive=(
                self.object.status == StockItem.Status.ACTIVE
                and self.object.current_quantity == 0
            ),
            can_reactivate=(
                self.object.status == StockItem.Status.ARCHIVED
                and self.object.project.status == Project.Status.ACTIVE
                and self.object.unit.is_active
            ),
            history_source_query=_source_query(self.request),
            import_rows=self.object.import_rows.select_related("job").filter(
                status="imported"
            )[:5],
        )
        return context


class StockAdditionView(InventoryWorkspaceMixin, View):
    template_name = "inventory/stock_addition_form.html"

    def get_initial(self):
        initial = {}
        stock_reference = self.request.GET.get("stock", "").strip()
        if stock_reference:
            item = _stock_item_from_reference(stock_reference)
            if item:
                supplier = Supplier.objects.filter(
                    normalized_name=item.normalized_supplier_name,
                    normalized_phone=item.normalized_supplier_phone,
                ).first()
                initial.update(
                    project=item.project,
                    material_name=item.material_name,
                    supplier=supplier,
                    unit=item.unit,
                    minimum_quantity=item.minimum_quantity,
                )
        project_code = self.request.GET.get("project", "").strip()
        if project_code and "project" not in initial:
            initial["project"] = active_projects().filter(code=project_code).first()
        return initial

    def get(self, request):
        form = StockAdditionForm(initial=self.get_initial())
        return render(request, self.template_name, self._context(form))

    def post(self, request):
        form = StockAdditionForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            try:
                result = add_stock(
                    user=request.user,
                    idempotency_key=data["idempotency_key"],
                    quantity=data["quantity"],
                    movement_date=data["movement_date"],
                    project=data["project"],
                    material_name=data["material_name"],
                    supplier_name=data["supplier"].name,
                    supplier_phone=data["supplier"].phone,
                    supplier_location=data["supplier"].location,
                    unit=data["unit"],
                    minimum_quantity=data["minimum_quantity"],
                    unit_price=data["unit_price"],
                    invoice_reference=data["invoice_reference"],
                    notes=data["notes"],
                    attachment=data["attachment"],
                    confirm_similar=data["confirm_similar"],
                )
            except InventoryOperationError as exc:
                form.add_error(None, _operation_error_message(exc))
            else:
                if result.duplicate_submission:
                    messages.info(request, "This stock addition was already recorded.")
                elif result.stock_item_created:
                    messages.success(request, "New stock record created and stock added safely.")
                else:
                    messages.success(request, "Stock was added safely.")
                return redirect(
                    "inventory:detail",
                    reference=result.movement.stock_item.reference,
                )
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "add-stock",
            "page_title": "Add stock",
            "page_subtitle": "Update an exact project stock record or create a new one.",
            "form": form,
            "exact_match": getattr(form, "exact_match", None),
            "similar_matches": getattr(form, "similar_matches", []),
        }


class StockUsageView(InventoryWorkspaceMixin, View):
    template_name = "inventory/stock_usage_form.html"

    def get_initial(self):
        initial = {}
        stock_reference = self.request.GET.get("stock", "").strip()
        if stock_reference:
            item = _stock_item_from_reference(stock_reference)
            if item:
                initial["project"] = item.project
                initial["stock_item"] = item
        project_code = self.request.GET.get("project", "").strip()
        if project_code and "project" not in initial:
            initial["project"] = active_projects().filter(code=project_code).first()
        return initial

    def get(self, request):
        form = StockUsageForm(initial=self.get_initial())
        return render(request, self.template_name, self._context(form))

    def post(self, request):
        form = StockUsageForm(request.POST, request.FILES)
        if form.is_valid():
            data = form.cleaned_data
            try:
                result = use_stock(
                    stock_item=data["stock_item"],
                    user=request.user,
                    idempotency_key=data["idempotency_key"],
                    quantity=data["quantity"],
                    movement_date=data["movement_date"],
                    purpose=data["purpose"],
                    recipient=data["recipient"],
                    invoice_reference=data["invoice_reference"],
                    notes=data["notes"],
                    attachment=data["attachment"],
                )
            except InventoryOperationError as exc:
                form.add_error(None, _operation_error_message(exc))
            else:
                if result.duplicate_submission:
                    messages.info(request, "This stock usage was already recorded.")
                else:
                    messages.success(request, "Stock usage was recorded safely.")
                return redirect(
                    "inventory:detail",
                    reference=result.movement.stock_item.reference,
                )
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        selected = None
        value = form["stock_item"].value()
        if value and str(value).isdigit():
            selected = stock_items().filter(pk=int(value)).first()
        return {
            "page_key": "remove-stock",
            "page_title": "Use stock",
            "page_subtitle": "Record project material usage without allowing negative stock.",
            "form": form,
            "selected_stock_item": selected,
        }


class StockAdjustmentView(InventoryWorkspaceMixin, View):
    template_name = "inventory/stock_adjustment_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.stock_item = get_object_or_404(
            stock_items(),
            reference=kwargs["reference"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = StockAdjustmentForm(stock_item=self.stock_item)
        return render(request, self.template_name, self._context(form))

    def post(self, request, *args, **kwargs):
        form = StockAdjustmentForm(request.POST, stock_item=self.stock_item)
        if form.is_valid():
            data = form.cleaned_data
            try:
                result = adjust_stock(
                    stock_item=self.stock_item,
                    user=request.user,
                    idempotency_key=data["idempotency_key"],
                    direction=data["direction"],
                    quantity=data["quantity"],
                    movement_date=data["movement_date"],
                    reason=data["reason"],
                    invoice_reference=data["invoice_reference"],
                    notes=data["notes"],
                )
            except InventoryOperationError as exc:
                form.add_error(None, _operation_error_message(exc))
            else:
                if result.duplicate_submission:
                    messages.info(request, "This adjustment was already recorded.")
                else:
                    messages.success(request, "Stock adjustment was recorded safely.")
                return redirect("inventory:detail", reference=self.stock_item.reference)
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "stock-detail",
            "page_title": "Adjust stock",
            "page_subtitle": "Correct a physical count while preserving a permanent history.",
            "stock_item": self.stock_item,
            "form": form,
        }


class StockMovementListView(InventoryWorkspaceMixin, ListView):
    model = StockMovement
    template_name = "inventory/movement_list.html"
    context_object_name = "movements"
    paginate_by = 50
    view_type = SavedView.ViewType.ACTIVITY

    def get_filter_form(self):
        data = _bound_filter_data(
            self.request,
            {"sort": "-date", "columns": DEFAULT_MOVEMENT_COLUMNS},
        )
        return MovementFilterForm(data)

    def get_queryset(self):
        queryset = stock_movements()
        self.filter_form = self.get_filter_form()
        if self.filter_form.is_valid():
            self.filter_data = self.filter_form.cleaned_data
            queryset = filter_stock_movements(queryset, self.filter_data)
            sort = self.filter_data.get("sort") or "-date"
            return queryset.order_by(*MOVEMENT_SORTS.get(sort, MOVEMENT_SORTS["-date"]))
        self.filter_data = {}
        return queryset.none()

    def get_visible_columns(self):
        requested = self.request.GET.getlist("columns")
        allowed = {value for value, _ in MovementFilterForm.COLUMN_CHOICES}
        selected = [value for value in requested if value in allowed]
        return tuple(selected) if selected else DEFAULT_MOVEMENT_COLUMNS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = self.filter_data
        advanced_keys = {
            "project_status", "material", "supplier", "supplier_phone", "quantity_min",
            "quantity_max", "price_min", "price_max", "reference", "purpose",
            "recipient", "reason", "created_by", "date_from", "date_to", "columns",
        }
        context.update(
            page_key="activity",
            page_title="Stock activity",
            page_subtitle=(
                "Search additions, usage, adjustments and reversals by every "
                "recorded field."
            ),
            filter_form=self.filter_form,
            filter_chips=_movement_filter_chips(self.request, data) if data else [],
            visible_columns=self.get_visible_columns(),
            current_sort=data.get("sort") or "-date",
            advanced_open=(
                bool(advanced_keys.intersection(self.request.GET.keys()))
                or not self.filter_form.is_valid()
            ),
            clear_url=reverse("core:activity"),
            saved_view_form=SavedViewCreateForm(),
            saved_view_type=self.view_type,
            source_query=_source_query(self.request),
            sort_choices=MovementFilterForm.SORT_CHOICES,
        )
        return context


class StockMovementDetailView(InventoryWorkspaceMixin, DetailView):
    model = StockMovement
    template_name = "inventory/movement_detail.html"
    context_object_name = "movement"
    slug_field = "reference"
    slug_url_kwarg = "reference"

    def get_queryset(self):
        return stock_movements()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="activity",
            page_title="Movement details",
            page_subtitle="An immutable inventory history record.",
        )
        return context


class MovementAttachmentView(InventoryWorkspaceMixin, View):
    def get(self, request, reference):
        movement = get_object_or_404(stock_movements(), reference=reference)
        if not movement.attachment:
            raise Http404("This movement has no attachment.")
        try:
            file_handle = movement.attachment.open("rb")
        except FileNotFoundError as exc:
            raise Http404("Attachment file was not found.") from exc
        filename = movement.attachment.name.rsplit("/", 1)[-1]
        response = FileResponse(file_handle, as_attachment=True, filename=filename)
        response["Cache-Control"] = "private, no-store"
        return response


class MovementReversalView(InventoryAdminRequiredMixin, View):
    template_name = "inventory/movement_reversal_form.html"

    def dispatch(self, request, *args, **kwargs):
        self.movement = get_object_or_404(
            stock_movements(),
            reference=kwargs["reference"],
        )
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        form = MovementReversalForm()
        return render(request, self.template_name, self._context(form))

    def post(self, request, *args, **kwargs):
        form = MovementReversalForm(request.POST)
        if form.is_valid():
            try:
                result = reverse_movement(
                    movement=self.movement,
                    user=request.user,
                    idempotency_key=form.cleaned_data["idempotency_key"],
                    movement_date=form.cleaned_data["movement_date"],
                    reason=form.cleaned_data["reason"],
                )
            except InventoryOperationError as exc:
                form.add_error(None, _operation_error_message(exc))
            else:
                if result.duplicate_submission:
                    messages.info(request, "This reversal was already recorded.")
                else:
                    messages.success(
                        request,
                        "Movement reversed with an opposite history entry.",
                    )
                return redirect(
                    "inventory:movement_detail",
                    reference=result.movement.reference,
                )
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "activity",
            "page_title": "Reverse movement",
            "page_subtitle": "Administrator-only corrective action. The original remains visible.",
            "movement": self.movement,
            "form": form,
        }


class LowStockListView(StockItemListView):
    template_name = "inventory/low_stock.html"
    view_type = SavedView.ViewType.LOW_STOCK

    def get_filter_form(self):
        data = _bound_filter_data(
            self.request,
            {
                "status": StockItem.Status.ACTIVE,
                "date_field": "latest_addition_date",
                "sort": "quantity",
                "columns": DEFAULT_STOCK_COLUMNS,
            },
        )
        form = StockItemFilterForm(data)
        form.fields["stock_status"].choices = (
            ("", "Low and out of stock"),
            ("low", "Low stock"),
            ("out", "Out of stock"),
        )
        return form

    def get_queryset(self):
        self.filter_form = self.get_filter_form()
        queryset = low_stock_items()
        if self.filter_form.is_valid():
            self.filter_data = self.filter_form.cleaned_data
            # Keep this view permanently scoped to active low/out-of-stock records.
            scoped = dict(self.filter_data)
            scoped["status"] = StockItem.Status.ACTIVE
            if scoped.get("stock_status") not in {"low", "out"}:
                scoped["stock_status"] = ""
            queryset = filter_stock_items(queryset, scoped)
            sort = scoped.get("sort") or "quantity"
            return queryset.order_by(*STOCK_SORTS.get(sort, STOCK_SORTS["quantity"]))
        self.filter_data = {}
        return queryset.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_chips"] = [
            {"label": "Low and out-of-stock scope", "clear_url": ""},
            *context.get("filter_chips", []),
        ]
        context.update(
            page_key="low-stock",
            page_title="Low stock",
            page_subtitle=(
                "Deep filtering for active records at or below their minimum quantity."
            ),
            clear_url=reverse("inventory:low_stock"),
            saved_view_type=self.view_type,
        )
        return context


class UnitListCreateView(InventoryWorkspaceMixin, View):
    template_name = "inventory/unit_list.html"

    def get(self, request):
        return render(request, self.template_name, self._context(UnitForm()))

    def post(self, request):
        form = UnitForm(request.POST)
        if form.is_valid():
            unit = form.save()
            messages.success(request, f"Unit {unit.name} was created.")
            return redirect("inventory:units")
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "units",
            "page_title": "Units",
            "page_subtitle": "Manage the labels used for stock quantities.",
            "form": form,
            "units": Unit.objects.annotate(stock_count=Count("stock_items")).order_by("name"),
        }


class UnitUpdateView(InventoryWorkspaceMixin, UpdateView):
    model = Unit
    form_class = UnitForm
    template_name = "inventory/unit_form.html"
    success_url = reverse_lazy("inventory:units")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Unit {self.object.name} was updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="units",
            page_title="Edit unit",
            page_subtitle="Existing stock keeps its unit relationship.",
            submit_label="Save unit",
        )
        return context


class SupplierListCreateView(InventoryWorkspaceMixin, View):
    template_name = "inventory/supplier_list.html"

    def get(self, request):
        return render(request, self.template_name, self._context(SupplierForm()))

    def post(self, request):
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save()
            messages.success(request, f"Supplier {supplier.name} was created.")
            return redirect("inventory:suppliers")
        return render(request, self.template_name, self._context(form), status=400)

    def _context(self, form):
        return {
            "page_key": "suppliers",
            "page_title": "Suppliers",
            "page_subtitle": "Manage reusable supplier details for faster stock entry.",
            "form": form,
            "suppliers": Supplier.objects.order_by("name", "phone"),
        }


class SupplierUpdateView(InventoryWorkspaceMixin, UpdateView):
    model = Supplier
    form_class = SupplierForm
    template_name = "inventory/supplier_form.html"
    success_url = reverse_lazy("inventory:suppliers")

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f"Supplier {self.object.name} was updated.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="suppliers",
            page_title="Edit supplier",
            page_subtitle="New stock entries will use these updated supplier details.",
            submit_label="Save supplier",
        )
        return context


class StockPickerAPIView(InventoryWorkspaceMixin, View):
    def get(self, request):
        project_identifier = request.GET.get("project", "").strip()
        query = request.GET.get("q", "").strip()
        if not project_identifier:
            return JsonResponse({"results": []})
        project = get_object_or_404(
            active_projects(),
            Q(code=project_identifier)
            | Q(pk=project_identifier if project_identifier.isdigit() else 0),
        )
        queryset = stock_items().filter(
            project=project,
            status=StockItem.Status.ACTIVE,
            current_quantity__gt=0,
        )
        queryset = apply_stock_search(queryset, query).order_by(
            "material_name", "supplier_name"
        )[:40]
        return JsonResponse(
            {
                "results": [
                    {
                        "id": item.pk,
                        "reference": str(item.reference),
                        "project_code": item.project.code,
                        "material_name": item.material_name,
                        "supplier_name": item.supplier_name,
                        "supplier_phone": item.supplier_phone,
                        "quantity": str(item.current_quantity),
                        "quantity_display": item.quantity_display,
                        "unit": item.unit.symbol,
                        "url": reverse(
                            "inventory:detail", kwargs={"reference": item.reference}
                        ),
                    }
                    for item in queryset
                ]
            }
        )


class StockMatchAPIView(InventoryWorkspaceMixin, View):
    def get(self, request):
        project_identifier = request.GET.get("project", "").strip()
        material_name = request.GET.get("material_name", "")
        supplier_name = request.GET.get("supplier_name", "")
        supplier_phone = request.GET.get("supplier_phone", "")
        if not all((project_identifier, material_name, supplier_name, supplier_phone)):
            return JsonResponse(
                {"error": "project, material_name, supplier_name and supplier_phone are required"},
                status=400,
            )
        project = get_object_or_404(
            active_projects(),
            Q(code=project_identifier)
            | Q(pk=project_identifier if project_identifier.isdigit() else 0),
        )
        result = find_stock_matches(
            project=project,
            material_name=material_name,
            supplier_name=supplier_name,
            supplier_phone=supplier_phone,
        )

        def serialize(item):
            return {
                "reference": str(item.reference),
                "project_code": item.project.code,
                "material_name": item.material_name,
                "supplier_name": item.supplier_name,
                "supplier_phone": item.supplier_phone,
                "unit": item.unit.symbol,
                "unit_id": item.unit_id,
                "current_quantity": str(item.current_quantity),
                "url": reverse("inventory:detail", kwargs={"reference": item.reference}),
            }

        return JsonResponse(
            {
                "exact": serialize(result.exact) if result.exact else None,
                "similar": [serialize(item) for item in result.similar],
            }
        )
