from __future__ import annotations

import uuid
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.forms import StyledForm, StyledModelForm
from apps.explorer.filtering import DATE_PRESETS
from apps.projects.models import Project

from .models import (
    InventoryLocation,
    StockItem,
    StockMovement,
    StockTransferLine,
    Supplier,
    Unit,
)
from .services.matching import find_stock_matches
from .services.transfers import TransferAllocation


def validate_uploaded_attachment(file):
    if not file:
        return file
    extension = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""
    if extension not in {"pdf", "jpg", "jpeg", "png"}:
        raise ValidationError("Upload a PDF, JPG, JPEG or PNG file.")
    if file.size > 10 * 1024 * 1024:
        raise ValidationError("Attachments must be 10 MB or smaller.")
    return file


class UnitForm(StyledModelForm):
    class Meta:
        model = Unit
        fields = ("name", "symbol", "is_active")


class SupplierForm(StyledModelForm):
    class Meta:
        model = Supplier
        fields = ("name", "phone", "location", "notes", "is_active")
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}


class SupplierSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value:
            supplier = getattr(value, "instance", None)
            if supplier:
                option["attrs"].update(
                    {
                        "data-name": supplier.name,
                        "data-phone": supplier.phone,
                        "data-location": supplier.location,
                    }
                )
        return option


class StockItemForm(StyledModelForm):
    attachment = forms.FileField(
        required=False,
        help_text="Optional PDF, JPG or PNG, maximum 10 MB.",
    )
    confirm_similar = forms.BooleanField(
        required=False,
        label="I reviewed the similar record and this is intentionally separate",
    )

    class Meta:
        model = StockItem
        fields = (
            "project",
            "material_name",
            "description",
            "supplier_name",
            "supplier_phone",
            "supplier_location",
            "unit",
            "minimum_quantity",
            "notes",
        )
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional size, grade, model, or specification",
                }
            ),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }
        labels = {"description": "Description / specification"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_projects = Project.objects.filter(
            status=Project.Status.ACTIVE, deleted_at__isnull=True
        )
        active_units = Unit.objects.filter(is_active=True, deleted_at__isnull=True)
        if self.instance.pk:
            active_projects = Project.objects.filter(deleted_at__isnull=True).filter(
                models.Q(status=Project.Status.ACTIVE) | models.Q(pk=self.instance.project_id)
            )
            active_units = Unit.objects.filter(deleted_at__isnull=True).filter(
                models.Q(is_active=True) | models.Q(pk=self.instance.unit_id)
            )
        self.fields["project"].queryset = active_projects.order_by("code")
        self.fields["unit"].queryset = active_units.order_by("name")
        if self.instance.pk and self.instance.movements.exists():
            self.fields["project"].disabled = True
            self.fields["project"].help_text = "Project is locked after the first stock movement."
            self.fields["unit"].disabled = True
            self.fields[
                "unit"
            ].help_text = (
                "Unit is locked after the first stock movement to keep quantities consistent."
            )
        self.exact_match = None
        self.similar_matches = []

    def clean_attachment(self):
        return validate_uploaded_attachment(self.cleaned_data.get("attachment"))

    def clean(self):
        cleaned_data = super().clean()
        required = ("project", "material_name", "supplier_name", "supplier_phone")
        if not all(cleaned_data.get(field) for field in required):
            return cleaned_data

        result = find_stock_matches(
            project=cleaned_data["project"],
            material_name=cleaned_data["material_name"],
            supplier_name=cleaned_data["supplier_name"],
            supplier_phone=cleaned_data["supplier_phone"],
            condition=self.instance.condition or StockItem.Condition.NEW,
            exclude_pk=self.instance.pk,
        )
        self.exact_match = result.exact
        self.similar_matches = list(result.similar)
        if result.exact:
            raise ValidationError(
                "An exact stock record already exists for this project. Open the existing "
                "record instead of creating a duplicate."
            )
        if self.similar_matches and not cleaned_data.get("confirm_similar"):
            raise ValidationError(
                "A similar stock record has the same project, material, and supplier but a "
                "different phone number. Review it and confirm that this record is separate."
            )
        return cleaned_data


class IdempotentMovementForm(StyledForm):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)
    movement_date = forms.DateField(
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("idempotency_key", uuid.uuid4())
        initial.setdefault("movement_date", timezone.localdate())
        super().__init__(*args, **kwargs)

    def clean_movement_date(self):
        value = self.cleaned_data["movement_date"]
        if value > timezone.localdate():
            raise ValidationError("Date cannot be in the future.")
        return value


class StockAdditionForm(IdempotentMovementForm):
    project = forms.ModelChoiceField(queryset=Project.objects.none())
    material_name = forms.CharField(max_length=180)
    description = forms.CharField(
        required=False,
        label="Description / specification",
        widget=forms.Textarea(
            attrs={
                "rows": 3,
                "placeholder": "Optional size, grade, model, or specification",
            }
        ),
    )
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.none(),
        widget=SupplierSelect,
        help_text="Choose a managed supplier; its phone and location are used automatically.",
    )
    unit = forms.ModelChoiceField(queryset=Unit.objects.none())
    minimum_quantity = forms.DecimalField(
        max_digits=16,
        decimal_places=3,
        min_value=Decimal("0"),
        initial=Decimal("0"),
        help_text="Used for low-stock warnings when a new record is created.",
    )
    quantity = forms.DecimalField(
        max_digits=16,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    unit_price = forms.DecimalField(
        max_digits=16,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
    )
    invoice_reference = forms.CharField(
        max_length=120,
        required=False,
        label="Invoice/reference",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    attachment = forms.FileField(
        required=False,
        help_text="Optional PDF, JPG or PNG, maximum 10 MB.",
    )
    confirm_similar = forms.BooleanField(
        required=False,
        label="I reviewed the similar record and this is intentionally separate",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(
            status=Project.Status.ACTIVE, deleted_at__isnull=True
        ).order_by("code")
        self.fields["unit"].queryset = Unit.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).order_by("name")
        self.fields["supplier"].queryset = Supplier.objects.filter(
            is_active=True, deleted_at__isnull=True
        ).order_by("name", "phone")
        self.exact_match = None
        self.similar_matches = []

    def clean_attachment(self):
        return validate_uploaded_attachment(self.cleaned_data.get("attachment"))

    def clean(self):
        cleaned_data = super().clean()
        required = ("project", "material_name", "supplier", "unit")
        if not all(cleaned_data.get(field) for field in required):
            return cleaned_data
        supplier = cleaned_data["supplier"]
        result = find_stock_matches(
            project=cleaned_data["project"],
            material_name=cleaned_data["material_name"],
            supplier_name=supplier.name,
            supplier_phone=supplier.phone,
        )
        self.exact_match = result.exact
        self.similar_matches = list(result.similar)
        if result.exact and result.exact.unit_id != cleaned_data["unit"].pk:
            self.add_error(
                "unit",
                f"The existing record uses {result.exact.unit.name} ({result.exact.unit.symbol}).",
            )
        if self.similar_matches and not cleaned_data.get("confirm_similar"):
            raise ValidationError(
                "A similar stock record has the same project, material, and supplier but a "
                "different phone number. Review it before creating a separate stock record."
            )
        return cleaned_data


class StockItemSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if value and getattr(value, "instance", None):
            item = value.instance
            option["attrs"].update(
                {
                    "data-balance": str(item.current_quantity),
                    "data-unit": item.unit.symbol,
                    "data-project": item.project.code,
                    "data-material": item.material_name,
                    "data-supplier": item.supplier_name,
                    "data-condition": item.get_condition_display(),
                }
            )
        return option


class StockItemChoiceField(forms.ModelChoiceField):
    widget = StockItemSelect

    def label_from_instance(self, item):
        return (
            f"{item.project.code} · {item.material_name} · {item.get_condition_display()} · "
            f"{item.supplier_name} "
            f"({item.quantity_display})"
        )


class StockUsageForm(IdempotentMovementForm):
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        label="Project",
        help_text="Choose the project before searching its available stock.",
    )
    stock_item = StockItemChoiceField(
        queryset=StockItem.objects.none(),
        label="Stock record",
        help_text="Searchable active stock with a positive balance.",
    )
    quantity = forms.DecimalField(
        max_digits=16,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    purpose = forms.CharField(max_length=180)
    recipient = forms.CharField(
        max_length=180,
        required=False,
        label="Recipient / work area",
    )
    invoice_reference = forms.CharField(max_length=120, required=False, label="Reference")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    attachment = forms.FileField(
        required=False,
        help_text="Optional PDF, JPG or PNG, maximum 10 MB.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(
            status=Project.Status.ACTIVE, deleted_at__isnull=True
        ).order_by("code")

        selected_item_id = None
        selected_project_id = None
        if self.is_bound:
            selected_item_id = self.data.get(self.add_prefix("stock_item"))
            selected_project_id = self.data.get(self.add_prefix("project"))
        else:
            initial_item = self.initial.get("stock_item")
            if isinstance(initial_item, StockItem):
                selected_item_id = initial_item.pk
                selected_project_id = initial_item.project_id
                self.initial.setdefault("project", initial_item.project)
            else:
                selected_item_id = getattr(initial_item, "pk", initial_item)
            initial_project = self.initial.get("project")
            if initial_project:
                selected_project_id = getattr(initial_project, "pk", initial_project)

        queryset = StockItem.objects.select_related("project", "unit").filter(
            status=StockItem.Status.ACTIVE,
            project__status=Project.Status.ACTIVE,
            deleted_at__isnull=True,
            project__deleted_at__isnull=True,
            current_quantity__gt=0,
        )
        if selected_project_id and str(selected_project_id).isdigit():
            queryset = queryset.filter(project_id=int(selected_project_id))
        elif selected_item_id and str(selected_item_id).isdigit():
            item_project = (
                StockItem.objects.filter(pk=int(selected_item_id))
                .values_list("project_id", flat=True)
                .first()
            )
            if item_project:
                queryset = queryset.filter(project_id=item_project)
        self.fields["stock_item"].queryset = queryset.order_by("material_name", "supplier_name")
        self.fields["project"].widget.attrs["data-stock-picker-project"] = ""
        self.fields["stock_item"].widget.attrs["data-stock-picker-select"] = ""

    def clean_attachment(self):
        return validate_uploaded_attachment(self.cleaned_data.get("attachment"))

    def clean(self):
        cleaned_data = super().clean()
        project = cleaned_data.get("project")
        item = cleaned_data.get("stock_item")
        quantity = cleaned_data.get("quantity")
        if item and project and item.project_id != project.pk:
            self.add_error("stock_item", "Choose a stock record from the selected project.")
        if item and quantity and quantity > item.current_quantity:
            self.add_error(
                "quantity",
                f"Only {item.quantity_display} is currently available.",
            )
        return cleaned_data


class StockAdjustmentForm(IdempotentMovementForm):
    DIRECTION_CHOICES = (
        ("increase", "Increase stock"),
        ("decrease", "Decrease stock"),
    )
    direction = forms.ChoiceField(choices=DIRECTION_CHOICES)
    quantity = forms.DecimalField(
        max_digits=16,
        decimal_places=3,
        min_value=Decimal("0.001"),
    )
    reason = forms.CharField(max_length=240)
    invoice_reference = forms.CharField(max_length=120, required=False, label="Reference")
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, stock_item: StockItem, **kwargs):
        self.stock_item = stock_item
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("direction") == "decrease"
            and cleaned_data.get("quantity")
            and cleaned_data["quantity"] > self.stock_item.current_quantity
        ):
            self.add_error(
                "quantity",
                f"Only {self.stock_item.quantity_display} is currently available.",
            )
        return cleaned_data


class MovementReversalForm(IdempotentMovementForm):
    reason = forms.CharField(
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Explain why the original movement must be reversed.",
    )


class StockTransferForm(StyledForm):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)
    source_location = forms.ModelChoiceField(
        queryset=InventoryLocation.objects.none(),
        label="From",
    )
    destination_location = forms.ModelChoiceField(
        queryset=InventoryLocation.objects.none(),
        label="To",
    )
    transfer_date = forms.DateField(
        label="Transfer date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    document_reference = forms.CharField(
        max_length=120,
        required=False,
        label="Reference",
    )
    attachment = forms.FileField(
        required=False,
        help_text="Optional PDF, JPG or PNG, maximum 10 MB.",
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    OUTCOMES = (
        StockTransferLine.Outcome.NEW,
        StockTransferLine.Outcome.USED,
        StockTransferLine.Outcome.NO_VALUE,
        StockTransferLine.Outcome.LOST,
    )

    def __init__(
        self,
        *args,
        source_location=None,
        require_full_transfer=False,
        lock_source=False,
        **kwargs,
    ):
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("idempotency_key", uuid.uuid4())
        initial.setdefault("transfer_date", timezone.localdate())
        if source_location:
            initial.setdefault("source_location", source_location)
        self.require_full_transfer = require_full_transfer
        self.lock_source = lock_source
        super().__init__(*args, **kwargs)
        locations = InventoryLocation.objects.select_related("project").filter(is_active=True)
        self.fields["source_location"].queryset = locations.order_by("location_type", "code")
        self.fields["destination_location"].queryset = locations.order_by(
            "location_type", "code"
        )
        if lock_source:
            self.fields["source_location"].disabled = True

        if not source_location:
            selected = self.data.get(self.add_prefix("source_location")) if self.is_bound else None
            if selected and str(selected).isdigit():
                source_location = locations.filter(pk=int(selected)).first()
            elif initial.get("source_location"):
                source_location = initial["source_location"]
        self.source_location = source_location
        self.source_items = []
        self.allocation_rows = []
        if source_location:
            self.source_items = list(
                StockItem.objects.select_related("unit", "location")
                .filter(
                    location=source_location,
                    status=StockItem.Status.ACTIVE,
                    deleted_at__isnull=True,
                    current_quantity__gt=0,
                )
                .order_by("material_name", "supplier_name", "condition")
            )
            for item in self.source_items:
                fields = []
                for outcome in self.OUTCOMES:
                    name = f"item_{item.pk}_{outcome}"
                    self.fields[name] = forms.DecimalField(
                        required=False,
                        min_value=Decimal("0"),
                        max_digits=16,
                        decimal_places=3,
                        label=StockTransferLine.Outcome(outcome).label,
                        widget=forms.NumberInput(
                            attrs={
                                "class": "input transfer-quantity",
                                "min": "0",
                                "step": "0.001",
                                "data-transfer-quantity": "",
                                "data-item": item.pk,
                                "data-outcome": outcome,
                            }
                        ),
                    )
                    fields.append(self[name])
                self.allocation_rows.append({"item": item, "fields": fields})

    def clean_attachment(self):
        return validate_uploaded_attachment(self.cleaned_data.get("attachment"))

    def clean_transfer_date(self):
        value = self.cleaned_data["transfer_date"]
        if value > timezone.localdate():
            raise ValidationError("Date cannot be in the future.")
        return value

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("source_location")
        destination = cleaned.get("destination_location")
        if source and destination and source.pk == destination.pk:
            self.add_error("destination_location", "Source and destination must be different.")
        self.allocations = []
        for row in self.allocation_rows:
            item = row["item"]
            total = Decimal("0")
            for outcome in self.OUTCOMES:
                name = f"item_{item.pk}_{outcome}"
                quantity = cleaned.get(name) or Decimal("0")
                total += quantity
                if quantity > 0:
                    self.allocations.append(TransferAllocation(item, outcome, quantity))
            if total > item.current_quantity:
                self.add_error(
                    f"item_{item.pk}_{self.OUTCOMES[-1]}",
                    f"Allocated {total:f}; only {item.quantity_display} is available.",
                )
            if self.require_full_transfer and total != item.current_quantity:
                self.add_error(
                    f"item_{item.pk}_{self.OUTCOMES[-1]}",
                    f"Project closeout requires all {item.quantity_display} to be allocated.",
                )
        if not self.allocations:
            raise ValidationError("Enter at least one New, Used, No value, or Lost quantity.")
        return cleaned


class StockTransferReversalForm(StyledForm):
    idempotency_key = forms.UUIDField(widget=forms.HiddenInput)
    reason = forms.CharField(
        max_length=240,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="Explain why both sides of this transfer must be reversed.",
    )

    def __init__(self, *args, **kwargs):
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("idempotency_key", uuid.uuid4())
        super().__init__(*args, **kwargs)


class DateRangeFilterForm(StyledForm):
    date_preset = forms.ChoiceField(required=False, choices=DATE_PRESETS, label="Period")
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="From date",
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="To date",
    )

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("date_from")
        end = cleaned.get("date_to")
        preset = cleaned.get("date_preset")
        if start and end and start > end:
            raise ValidationError("Start date cannot be after end date.")
        if preset and preset != "custom":
            cleaned["date_from"] = None
            cleaned["date_to"] = None
        elif start or end:
            cleaned["date_preset"] = "custom"
        if preset == "custom" and not (start or end):
            self.add_error("date_from", "Choose at least one custom date boundary.")
        return cleaned


class StockItemFilterForm(DateRangeFilterForm):
    STOCK_STATUS_CHOICES = (
        ("", "Any stock status"),
        ("in", "In stock"),
        ("low", "Low stock"),
        ("out", "Out of stock"),
    )
    RECORD_STATUS_CHOICES = (
        (StockItem.Status.ACTIVE, "Active records"),
        ("all", "Active and archived"),
        (StockItem.Status.ARCHIVED, "Archived records"),
    )
    PROJECT_STATUS_CHOICES = (
        ("", "Any project status"),
        *Project.Status.choices,
    )
    DATE_FIELD_CHOICES = (
        ("latest_addition_date", "Latest addition date"),
        ("created_at", "Record created date"),
        ("updated_at", "Last updated date"),
    )
    SORT_CHOICES = (
        ("updated", "Recently updated"),
        ("created", "Newest records"),
        ("project", "Sort by project"),
        ("material", "Sort by material A–Z"),
        ("-material", "Sort by material Z–A"),
        ("supplier", "Sort by supplier A–Z"),
        ("-supplier", "Sort by supplier Z–A"),
        ("quantity", "Sort by quantity: low first"),
        ("-quantity", "Sort by quantity: high first"),
        ("minimum", "Sort by minimum: low first"),
        ("-minimum", "Sort by minimum: high first"),
        ("price", "Sort by price: low first"),
        ("-price", "Sort by price: high first"),
        ("value", "Sort by stock value: low first"),
        ("-value", "Sort by stock value: high first"),
        ("latest-addition", "Sort by latest addition: newest"),
        ("oldest-addition", "Sort by latest addition: oldest"),
    )
    COLUMN_CHOICES = (
        ("project", "Location"),
        ("condition", "Condition"),
        ("material", "Material"),
        ("description", "Description"),
        ("supplier", "Supplier"),
        ("phone", "Supplier phone"),
        ("location", "Supplier location"),
        ("quantity", "Quantity"),
        ("minimum", "Minimum"),
        ("unit", "Unit"),
        ("price", "Latest price"),
        ("value", "Stock value"),
        ("latest_addition", "Latest addition"),
        ("stock_status", "Stock status"),
        ("updated", "Updated"),
        ("created", "Created"),
    )

    q = forms.CharField(required=False, label="Search all fields")
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        to_field_name="code",
        required=False,
        empty_label="All projects",
        label="Project",
    )
    location = forms.ModelChoiceField(
        queryset=InventoryLocation.objects.none(),
        to_field_name="code",
        required=False,
        empty_label="All locations",
        label="Location",
    )
    condition = forms.MultipleChoiceField(
        required=False,
        choices=StockItem.Condition.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Conditions",
    )
    project_status = forms.ChoiceField(
        required=False,
        choices=PROJECT_STATUS_CHOICES,
        label="Project status",
    )
    material = forms.CharField(required=False, label="Material name")
    description = forms.CharField(required=False)
    supplier = forms.CharField(required=False, label="Supplier name")
    supplier_phone = forms.CharField(required=False)
    supplier_location = forms.CharField(required=False)
    unit = forms.ModelMultipleChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Units",
    )
    stock_status = forms.ChoiceField(required=False, choices=STOCK_STATUS_CHOICES)
    status = forms.ChoiceField(required=False, choices=RECORD_STATUS_CHOICES)
    quantity_min = forms.DecimalField(required=False, decimal_places=3, label="Quantity minimum")
    quantity_max = forms.DecimalField(required=False, decimal_places=3, label="Quantity maximum")
    minimum_min = forms.DecimalField(
        required=False,
        decimal_places=3,
        label="Configured minimum from",
    )
    minimum_max = forms.DecimalField(
        required=False,
        decimal_places=3,
        label="Configured minimum to",
    )
    price_min = forms.DecimalField(required=False, decimal_places=2, label="Latest price minimum")
    price_max = forms.DecimalField(required=False, decimal_places=2, label="Latest price maximum")
    date_field = forms.ChoiceField(required=False, choices=DATE_FIELD_CHOICES)
    created_by = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False, empty_label="Any creator"
    )
    updated_by = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False, empty_label="Any updater"
    )
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)
    columns = forms.MultipleChoiceField(
        required=False,
        choices=COLUMN_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Visible columns",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(deleted_at__isnull=True).order_by(
            "code"
        )
        self.fields["location"].queryset = InventoryLocation.objects.filter(
            is_active=True
        ).order_by("location_type", "code")
        self.fields["unit"].queryset = Unit.objects.filter(deleted_at__isnull=True).order_by("name")
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": (
                    "Search project, material, description, supplier, unit, notes, or user…"
                ),
                "autocomplete": "off",
                "aria-label": "Search inventory",
                "data-live-filter-search": "",
            }
        )
        users = (
            get_user_model()
            .objects.filter(is_active=True)
            .order_by(
                "first_name",
                "username",
            )
        )
        self.fields["created_by"].queryset = users
        self.fields["updated_by"].queryset = users
        self.fields["status"].initial = StockItem.Status.ACTIVE
        self.fields["date_field"].initial = "latest_addition_date"
        self.fields["sort"].initial = "project"

    def clean(self):
        cleaned = super().clean()
        for lower, upper, label in (
            ("quantity_min", "quantity_max", "Quantity"),
            ("minimum_min", "minimum_max", "Configured minimum"),
            ("price_min", "price_max", "Price"),
        ):
            if cleaned.get(lower) is not None and cleaned.get(upper) is not None:
                if cleaned[lower] > cleaned[upper]:
                    self.add_error(upper, f"{label} maximum cannot be below its minimum.")
        return cleaned


class MovementFilterForm(DateRangeFilterForm):
    SORT_CHOICES = (
        ("-date", "Date: newest first"),
        ("date", "Date: oldest first"),
        ("project", "Project"),
        ("material", "Material"),
        ("type", "Action"),
        ("quantity", "Quantity: low first"),
        ("-quantity", "Quantity: high first"),
        ("user", "Storekeeper"),
    )
    COLUMN_CHOICES = (
        ("date", "Date"),
        ("project", "Location"),
        ("condition", "Condition"),
        ("material", "Material"),
        ("supplier", "Supplier"),
        ("phone", "Supplier phone"),
        ("type", "Action"),
        ("quantity", "Quantity"),
        ("balance", "Balance"),
        ("price", "Unit price"),
        ("reference", "Reference / purpose"),
        ("user", "User"),
    )

    q = forms.CharField(required=False, label="Search all fields")
    project = forms.ModelMultipleChoiceField(
        queryset=Project.objects.none(),
        to_field_name="code",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Projects",
    )
    location = forms.ModelMultipleChoiceField(
        queryset=InventoryLocation.objects.none(),
        to_field_name="code",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Locations",
    )
    condition = forms.MultipleChoiceField(
        required=False,
        choices=StockItem.Condition.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Conditions",
    )
    project_status = forms.ChoiceField(
        required=False,
        choices=(("", "Any project status"), *Project.Status.choices),
    )
    material = forms.CharField(required=False, label="Material name")
    supplier = forms.CharField(required=False, label="Supplier name")
    supplier_phone = forms.CharField(required=False)
    movement_type = forms.MultipleChoiceField(
        required=False,
        choices=StockMovement.Type.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Actions",
    )
    quantity_min = forms.DecimalField(required=False, decimal_places=3, label="Quantity minimum")
    quantity_max = forms.DecimalField(required=False, decimal_places=3, label="Quantity maximum")
    price_min = forms.DecimalField(required=False, decimal_places=2, label="Unit price minimum")
    price_max = forms.DecimalField(required=False, decimal_places=2, label="Unit price maximum")
    reference = forms.CharField(required=False, label="Invoice / reference")
    purpose = forms.CharField(required=False)
    recipient = forms.CharField(required=False, label="Recipient / work area")
    reason = forms.CharField(required=False)
    created_by = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False, empty_label="Any user"
    )
    sort = forms.ChoiceField(required=False, choices=SORT_CHOICES)
    columns = forms.MultipleChoiceField(
        required=False,
        choices=COLUMN_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Visible columns",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = Project.objects.filter(deleted_at__isnull=True).order_by(
            "code"
        )
        self.fields["location"].queryset = InventoryLocation.objects.order_by(
            "location_type", "code"
        )
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": ("Search project, material, supplier, reference, purpose, or user…"),
                "autocomplete": "off",
                "aria-label": "Search stock activity",
                "data-live-filter-search": "",
            }
        )
        self.fields["created_by"].queryset = (
            get_user_model().objects.filter(is_active=True).order_by("first_name", "username")
        )
        self.fields["sort"].initial = "-date"

    def clean(self):
        cleaned = super().clean()
        for lower, upper, label in (
            ("quantity_min", "quantity_max", "Quantity"),
            ("price_min", "price_max", "Price"),
        ):
            if cleaned.get(lower) is not None and cleaned.get(upper) is not None:
                if cleaned[lower] > cleaned[upper]:
                    self.add_error(upper, f"{label} maximum cannot be below its minimum.")
        return cleaned


class StockHistoryFilterForm(DateRangeFilterForm):
    q = forms.CharField(required=False, label="Search history")
    movement_type = forms.MultipleChoiceField(
        required=False,
        choices=StockMovement.Type.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Actions",
    )
    created_by = forms.ModelChoiceField(
        queryset=get_user_model().objects.none(), required=False, empty_label="Any user"
    )
    sort = forms.ChoiceField(
        required=False,
        choices=(("-date", "Newest first"), ("date", "Oldest first")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["q"].widget.attrs.update(
            {
                "placeholder": "Search reference, purpose, recipient, reason, or notes…",
                "autocomplete": "off",
            }
        )
        self.fields["created_by"].queryset = (
            get_user_model().objects.filter(is_active=True).order_by("first_name", "username")
        )
        self.fields["sort"].initial = "-date"
