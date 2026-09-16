from __future__ import annotations

from django import forms
from django.db.models import Q

from .models import (
    SourcingAvailability,
    SourcingMaterial,
    SourcingManpowerSupplier,
    SourcingManpowerContact,
    SourcingRateBasis,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
)


class SourcingVendorForm(forms.ModelForm):
    class Meta:
        model = SourcingVendor
        fields = (
            "code",
            "name",
            "display_name",
            "primary_contact_name",
            "phone",
            "mobile",
            "email",
            "city",
            "region",
            "cr_number",
            "vat_number",
            "website",
            "notes",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "VND-XXXXXX", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"placeholder": "Legal / company name", "autocomplete": "organization"}),
            "display_name": forms.TextInput(attrs={"placeholder": "Name shown in Sourcing Directory"}),
            "primary_contact_name": forms.TextInput(attrs={"placeholder": "Primary contact person", "autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "mobile": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"placeholder": "vendor@example.com", "autocomplete": "email"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "region": forms.TextInput(attrs={"placeholder": "Region"}),
            "cr_number": forms.TextInput(attrs={"placeholder": "Commercial Registration"}),
            "vat_number": forms.TextInput(attrs={"placeholder": "VAT number"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference-only sourcing notes"}),
        }
        labels = {
            "name": "Company / Vendor Name",
            "display_name": "Display Name",
            "primary_contact_name": "Primary Contact",
            "cr_number": "CR Number",
            "vat_number": "VAT Number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Reference code unique inside this company."
        self.fields["display_name"].help_text = "Leave blank to use the company/vendor name."


class SourcingVendorContactForm(forms.ModelForm):
    class Meta:
        model = SourcingVendorContact
        fields = (
            "salutation",
            "first_name",
            "last_name",
            "designation",
            "department",
            "email",
            "work_phone",
            "mobile",
            "is_primary",
        )
        widgets = {
            "salutation": forms.TextInput(attrs={"placeholder": "Mr / Ms"}),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "designation": forms.TextInput(attrs={"placeholder": "Sales Manager"}),
            "department": forms.TextInput(attrs={"placeholder": "Sales / Procurement"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "work_phone": forms.TextInput(attrs={"autocomplete": "tel"}),
            "mobile": forms.TextInput(attrs={"autocomplete": "tel"}),
        }
        labels = {
            "work_phone": "Work Phone",
            "is_primary": "Primary Contact",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "is_primary":
                field.widget.attrs.setdefault("class", "sourcing-input")


class SourcingManpowerSupplierForm(forms.ModelForm):
    class Meta:
        model = SourcingManpowerSupplier
        fields = (
            "code",
            "name",
            "primary_contact_name",
            "phone",
            "mobile",
            "email",
            "city",
            "region",
            "cr_number",
            "vat_number",
            "notes",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "MPS-XXXXXX", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"placeholder": "Manpower supplier / company name", "autocomplete": "organization"}),
            "primary_contact_name": forms.TextInput(attrs={"placeholder": "Primary contact person", "autocomplete": "name"}),
            "phone": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "mobile": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"placeholder": "supplier@example.com", "autocomplete": "email"}),
            "city": forms.TextInput(attrs={"placeholder": "City"}),
            "region": forms.TextInput(attrs={"placeholder": "Region"}),
            "cr_number": forms.TextInput(attrs={"placeholder": "Commercial Registration"}),
            "vat_number": forms.TextInput(attrs={"placeholder": "VAT number"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference-only manpower sourcing notes"}),
        }
        labels = {
            "name": "Company / Supplier Name",
            "primary_contact_name": "Primary Contact",
            "cr_number": "CR Number",
            "vat_number": "VAT Number",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Independent Sourcing code; it is not a Rental Payroll supplier code."


class SourcingManpowerContactForm(forms.ModelForm):
    class Meta:
        model = SourcingManpowerContact
        fields = (
            "salutation",
            "first_name",
            "last_name",
            "designation",
            "department",
            "email",
            "work_phone",
            "mobile",
            "is_primary",
        )
        widgets = {
            "salutation": forms.TextInput(attrs={"placeholder": "Mr / Ms"}),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "designation": forms.TextInput(attrs={"placeholder": "Sales / Operations Manager"}),
            "department": forms.TextInput(attrs={"placeholder": "Operations / Business Development"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "work_phone": forms.TextInput(attrs={"autocomplete": "tel"}),
            "mobile": forms.TextInput(attrs={"autocomplete": "tel"}),
        }
        labels = {
            "work_phone": "Work Phone",
            "is_primary": "Primary Contact",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name != "is_primary":
                field.widget.attrs.setdefault("class", "sourcing-input")


class SourcingTradeForm(forms.ModelForm):
    aliases = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "One alias per line, e.g.\nA/C Technician\nAir Conditioning Technician",
            }
        ),
        help_text="Optional worker-type search aliases. One alias per line or comma-separated.",
    )

    class Meta:
        model = SourcingTrade
        fields = ("code", "name", "category", "aliases", "notes")
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "TRD-XXXX", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"placeholder": "Steel Fixer, Electrician, AC Technician ...", "autocomplete": "off"}),
            "category": forms.TextInput(attrs={"placeholder": "Civil, Electrical, HVAC, Engineering ..."}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference notes for this worker type / trade"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["aliases"] = "\n".join(self.instance.aliases or [])
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Independent Sourcing code; it is not a Payroll occupation or employee code."

    def clean_aliases(self):
        raw = str(self.cleaned_data.get("aliases") or "")
        values = []
        seen = set()
        for chunk in raw.replace(",", "\n").splitlines():
            value = " ".join(chunk.strip().split())
            key = value.casefold()
            if value and key not in seen:
                values.append(value)
                seen.add(key)
        return values


class SourcingWorkforceOfferForm(forms.ModelForm):
    verified_now = forms.BooleanField(
        required=False,
        label="Verified now",
        help_text="Mark this workforce quantity/rate as confirmed now. Leave off when only correcting reference text.",
    )
    contact_name = forms.CharField(
        required=False,
        max_length=160,
        label="Spoke With",
        widget=forms.TextInput(attrs={"placeholder": "Supplier contact name (optional)"}),
    )

    class Meta:
        model = SourcingWorkforceOffer
        fields = (
            "trade",
            "availability",
            "available_quantity",
            "rate",
            "currency",
            "rate_basis",
            "overtime_rate",
            "rate_valid_until",
            "mobilization_lead_time",
            "work_location",
            "verification_note",
            "notes",
        )
        widgets = {
            "trade": forms.Select(),
            "availability": forms.Select(choices=SourcingAvailability.choices),
            "available_quantity": forms.NumberInput(attrs={"step": "1", "min": "0", "placeholder": "Blank = unknown"}),
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank = unknown"}),
            "currency": forms.TextInput(attrs={"maxlength": "3", "placeholder": "SAR"}),
            "rate_basis": forms.Select(choices=SourcingRateBasis.choices),
            "overtime_rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Optional"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "mobilization_lead_time": forms.TextInput(attrs={"placeholder": "Immediate, 2 days, 1 week ..."}),
            "work_location": forms.TextInput(attrs={"placeholder": "Dammam, Jubail, Eastern Region ..."}),
            "verification_note": forms.TextInput(attrs={"placeholder": "What the supplier confirmed / conditions"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference-only workforce notes"}),
        }
        labels = {
            "available_quantity": "Available Workers",
            "rate": "Standard Rate",
            "rate_basis": "Rate Basis",
            "overtime_rate": "Overtime Rate",
            "rate_valid_until": "Rate Valid Until",
            "mobilization_lead_time": "Mobilization / Lead Time",
            "work_location": "Work Location / Coverage",
            "verification_note": "Verification Note",
        }

    def __init__(self, *args, company=None, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is None:
            self.fields["trade"].queryset = SourcingTrade.objects.none()
        else:
            queryset = SourcingTrade.objects.for_company(company)
            if self.instance and self.instance.pk and self.instance.trade_id:
                queryset = queryset.filter(Q(is_active=True) | Q(pk=self.instance.trade_id))
            else:
                queryset = queryset.filter(is_active=True)
            self.fields["trade"].queryset = queryset.order_by("category", "name", "code")
        for name, field in self.fields.items():
            if name != "verified_now":
                field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["trade"].empty_label = "Select Worker Type / Trade"
        self.fields["trade"].help_text = "Trades are controlled in the independent Sourcing Reference master."
        self.fields["available_quantity"].help_text = "Leave blank when the supplier did not confirm a quantity. This is not a Rental worker count."
        self.fields["rate"].help_text = "Reference sourcing rate only. It never changes Payroll or supplier settlement rates."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            self.initial.setdefault("rate_basis", getattr(self.instance, "rate_basis", None) or SourcingRateBasis.MONTH)
            if supplier is not None:
                self.initial.setdefault("contact_name", getattr(supplier, "primary_contact_name", "") or "")
            if not (self.instance and self.instance.pk):
                self.initial["verified_now"] = True


class SourcingWorkforceOfferVerificationForm(forms.ModelForm):
    contact_name = forms.CharField(
        required=False,
        max_length=160,
        label="Spoke With",
        widget=forms.TextInput(attrs={"placeholder": "Supplier contact name (optional)"}),
        help_text="Who confirmed the workforce quantity/rate, if known.",
    )

    class Meta:
        model = SourcingWorkforceOffer
        fields = (
            "availability",
            "available_quantity",
            "rate",
            "currency",
            "rate_basis",
            "overtime_rate",
            "rate_valid_until",
            "mobilization_lead_time",
            "work_location",
            "verification_note",
        )
        widgets = {
            "availability": forms.Select(choices=SourcingAvailability.choices),
            "available_quantity": forms.NumberInput(attrs={"step": "1", "min": "0", "placeholder": "Blank = unknown"}),
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank = unknown"}),
            "currency": forms.TextInput(attrs={"maxlength": "3", "placeholder": "SAR"}),
            "rate_basis": forms.Select(choices=SourcingRateBasis.choices),
            "overtime_rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Optional"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "mobilization_lead_time": forms.TextInput(attrs={"placeholder": "Immediate, 2 days, 1 week ..."}),
            "work_location": forms.TextInput(attrs={"placeholder": "Dammam, Jubail, Eastern Region ..."}),
            "verification_note": forms.TextInput(attrs={"placeholder": "What the supplier confirmed / conditions"}),
        }
        labels = {
            "available_quantity": "Available Workers",
            "rate": "Standard Rate",
            "rate_basis": "Rate Basis",
            "overtime_rate": "Overtime Rate",
            "rate_valid_until": "Rate Valid Until",
            "mobilization_lead_time": "Mobilization / Lead Time",
            "work_location": "Work Location / Coverage",
            "verification_note": "Verification Note",
        }

    def __init__(self, *args, supplier=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["available_quantity"].help_text = "Leave blank when the supplier did not confirm a quantity."
        self.fields["rate"].help_text = "Reference sourcing rate only. It never changes Payroll or settlement rates."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if supplier is not None:
                self.initial.setdefault("contact_name", getattr(supplier, "primary_contact_name", "") or "")


class SourcingMaterialForm(forms.ModelForm):
    aliases = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "One alias per line, e.g.\nReinforcement Bar\nSteel Bar",
            }
        ),
        help_text="Optional search aliases. One alias per line or comma-separated.",
    )

    class Meta:
        model = SourcingMaterial
        fields = ("code", "name", "category", "default_unit", "aliases", "notes")
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "MAT-XXXX", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"placeholder": "Material / item name", "autocomplete": "off"}),
            "category": forms.TextInput(attrs={"placeholder": "Civil, Electrical, HVAC, PPE ..."}),
            "default_unit": forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ..."}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference notes for this Sourcing Material"}),
        }
        labels = {"default_unit": "Default Unit"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["aliases"] = "\n".join(self.instance.aliases or [])
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Independent Sourcing code; it is not an Inventory item code."

    def clean_aliases(self):
        raw = str(self.cleaned_data.get("aliases") or "")
        values = []
        seen = set()
        for chunk in raw.replace(",", "\n").splitlines():
            value = " ".join(chunk.strip().split())
            key = value.casefold()
            if value and key not in seen:
                values.append(value)
                seen.add(key)
        return values


class SourcingVendorOfferForm(forms.ModelForm):
    verified_now = forms.BooleanField(
        required=False,
        label="Verified now",
        help_text="Mark the quantity/rate as confirmed now. Leave off when only correcting reference text.",
    )
    contact_name = forms.CharField(
        required=False,
        max_length=160,
        label="Spoke With",
        widget=forms.TextInput(attrs={"placeholder": "Vendor contact name (optional)"}),
    )

    class Meta:
        model = SourcingVendorOffer
        fields = (
            "material",
            "specification",
            "brand",
            "model",
            "available_quantity",
            "unit",
            "minimum_quantity",
            "availability",
            "rate",
            "currency",
            "rate_valid_until",
            "lead_time",
            "verification_note",
            "notes",
        )
        widgets = {
            "material": forms.Select(),
            "specification": forms.TextInput(attrs={"placeholder": "Size, grade, capacity, standard ..."}),
            "brand": forms.TextInput(attrs={"placeholder": "Brand (optional)"}),
            "model": forms.TextInput(attrs={"placeholder": "Model (optional)"}),
            "available_quantity": forms.NumberInput(attrs={"step": "0.001", "min": "0", "placeholder": "Blank = unknown"}),
            "unit": forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ..."}),
            "minimum_quantity": forms.NumberInput(attrs={"step": "0.001", "min": "0", "placeholder": "Optional"}),
            "availability": forms.Select(choices=SourcingAvailability.choices),
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank = unknown"}),
            "currency": forms.TextInput(attrs={"maxlength": "3", "placeholder": "SAR"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "lead_time": forms.TextInput(attrs={"placeholder": "Immediate, 1 day, 2 weeks ..."}),
            "verification_note": forms.TextInput(attrs={"placeholder": "Short confirmation note"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference-only offer notes"}),
        }
        labels = {
            "available_quantity": "Available Qty",
            "minimum_quantity": "Minimum Order Qty",
            "rate_valid_until": "Rate Valid Until",
            "verification_note": "Verification Note",
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is None:
            self.fields["material"].queryset = SourcingMaterial.objects.none()
        else:
            queryset = SourcingMaterial.objects.for_company(company)
            if self.instance and self.instance.pk and self.instance.material_id:
                queryset = queryset.filter(Q(is_active=True) | Q(pk=self.instance.material_id))
            else:
                queryset = queryset.filter(is_active=True)
            self.fields["material"].queryset = queryset.order_by("category", "name", "code")
        for name, field in self.fields.items():
            if name != "verified_now":
                field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["material"].empty_label = "Select Sourcing Material"
        self.fields["material"].help_text = "Materials are managed in the independent Sourcing reference master."
        self.fields["available_quantity"].help_text = "Leave blank when the Vendor did not confirm quantity."
        self.fields["rate"].help_text = "Reference quote only. It never posts to Inventory or Accounting."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if not (self.instance and self.instance.pk):
                self.initial["verified_now"] = True


class SourcingVendorOfferVerificationForm(forms.ModelForm):
    contact_name = forms.CharField(
        required=False,
        max_length=160,
        label="Spoke With",
        widget=forms.TextInput(attrs={"placeholder": "Vendor contact name (optional)"}),
        help_text="Who confirmed the quantity/rate, if known.",
    )

    class Meta:
        model = SourcingVendorOffer
        fields = (
            "availability",
            "available_quantity",
            "unit",
            "minimum_quantity",
            "rate",
            "currency",
            "rate_valid_until",
            "lead_time",
            "verification_note",
        )
        widgets = {
            "availability": forms.Select(choices=SourcingAvailability.choices),
            "available_quantity": forms.NumberInput(attrs={"step": "0.001", "min": "0", "placeholder": "Blank = unknown"}),
            "unit": forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ..."}),
            "minimum_quantity": forms.NumberInput(attrs={"step": "0.001", "min": "0", "placeholder": "Optional"}),
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank = unknown"}),
            "currency": forms.TextInput(attrs={"maxlength": "3", "placeholder": "SAR"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "lead_time": forms.TextInput(attrs={"placeholder": "Immediate, 1 day, 2 weeks ..."}),
            "verification_note": forms.TextInput(attrs={"placeholder": "What the Vendor confirmed / conditions"}),
        }
        labels = {
            "available_quantity": "Available Qty",
            "minimum_quantity": "Minimum Order Qty",
            "rate_valid_until": "Rate Valid Until",
            "verification_note": "Verification Note",
        }

    def __init__(self, *args, vendor=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["available_quantity"].help_text = "Leave blank when the Vendor did not confirm a quantity."
        self.fields["rate"].help_text = "Reference quote only. It never posts to Inventory or Accounting."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if vendor is not None:
                self.initial.setdefault("contact_name", getattr(vendor, "primary_contact_name", "") or "")


class SourcingImportUploadForm(forms.Form):
    dataset = forms.ChoiceField(choices=(), label="Import Dataset")
    file = forms.FileField(
        label="CSV or XLSX file",
        help_text="Maximum 2 MB and 5,000 data rows. Imports are all-or-nothing.",
    )
    dry_run = forms.BooleanField(
        required=False,
        initial=True,
        label="Validate only (recommended first)",
        help_text="Runs the complete import inside a rollback-only transaction and reports row-level results without changing Sourcing data.",
    )

    def __init__(self, *args, dataset_choices=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["dataset"].choices = tuple(dataset_choices)
        self.fields["dataset"].widget.attrs.setdefault("class", "sourcing-input")
        self.fields["file"].widget.attrs.setdefault("class", "sourcing-input")
