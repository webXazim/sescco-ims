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
from .models.base import clean_text, normalize_text


NEW_MATERIAL_CATEGORY_VALUE = "__new__"


def sourcing_material_categories(company) -> list[str]:
    """Return the company's controlled material category/type vocabulary.

    ``SourcingMaterial.category`` intentionally remains a simple text field so this
    upgrade does not introduce a schema migration.  The UI treats the distinct
    values already used by the company as the selectable category/type master.
    """
    if company is None:
        return []
    raw_values = (
        SourcingMaterial.objects.for_company(company)
        .exclude(category="")
        .order_by("category")
        .values_list("category", flat=True)
        .distinct()
    )
    categories: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        value = clean_text(raw)
        key = value.casefold()
        if value and key not in seen:
            categories.append(value)
            seen.add(key)
    return categories


def _material_category_choices(*, categories=(), current: str = "", posted: str = ""):
    values: list[str] = []
    seen: set[str] = set()
    for raw in [*categories, current, posted]:
        value = clean_text(raw)
        if not value or value == NEW_MATERIAL_CATEGORY_VALUE:
            continue
        key = value.casefold()
        if key not in seen:
            values.append(value)
            seen.add(key)
    values.sort(key=str.casefold)
    return [
        ("", "No category / type"),
        *((value, value) for value in values),
        (NEW_MATERIAL_CATEGORY_VALUE, "+ Add new category / type"),
    ]


def _canonical_material_category(value: object, categories=()) -> str:
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    key = cleaned.casefold()
    for existing in categories:
        candidate = clean_text(existing)
        if candidate and candidate.casefold() == key:
            return candidate
    return cleaned


class SourcingVendorForm(forms.ModelForm):
    materials = forms.ModelMultipleChoiceField(
        queryset=SourcingMaterial.objects.none(),
        required=False,
        label="Materials",
        widget=forms.CheckboxSelectMultiple,
        help_text=(
            "Select the material types this Vendor can supply. They are added to the Vendor Supply Catalog "
            "with availability left as Unknown so details can be completed later."
        ),
    )

    class Meta:
        model = SourcingVendor
        fields = (
            "code",
            "name",
            "display_name",
            "cr_number",
            "vat_number",
            "company_phone",
            "company_email",
            "website",
            "primary_contact_name",
            "mobile",
            "email",
            "address",
            "street_number",
            "district",
            "city",
            "region",
            "postal_code",
            "notes",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "VND-XXXXXX", "autocomplete": "off"}),
            "name": forms.TextInput(attrs={"placeholder": "Legal / company name", "autocomplete": "organization"}),
            "display_name": forms.TextInput(attrs={"placeholder": "Name shown in Sourcing Directory"}),
            "cr_number": forms.TextInput(attrs={"placeholder": "Commercial Registration"}),
            "vat_number": forms.TextInput(attrs={"placeholder": "VAT number"}),
            "company_phone": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "company_email": forms.EmailInput(attrs={"placeholder": "info@vendor.com", "autocomplete": "email"}),
            "website": forms.URLInput(attrs={"placeholder": "https://"}),
            "primary_contact_name": forms.TextInput(attrs={"placeholder": "Primary contact person", "autocomplete": "name"}),
            "mobile": forms.TextInput(attrs={"placeholder": "+966 ...", "autocomplete": "tel"}),
            "email": forms.EmailInput(attrs={"placeholder": "contact@vendor.com", "autocomplete": "email"}),
            "address": forms.TextInput(attrs={"placeholder": "Street / building / address line", "autocomplete": "street-address"}),
            "street_number": forms.TextInput(attrs={"placeholder": "Street number", "autocomplete": "address-line2"}),
            "district": forms.TextInput(attrs={"placeholder": "District"}),
            "city": forms.TextInput(attrs={"placeholder": "City", "autocomplete": "address-level2"}),
            "region": forms.TextInput(attrs={"placeholder": "Region / Province", "autocomplete": "address-level1"}),
            "postal_code": forms.TextInput(attrs={"placeholder": "Postal code", "autocomplete": "postal-code"}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference-only sourcing notes"}),
        }
        labels = {
            "name": "Company / Vendor Name",
            "display_name": "Display Name",
            "cr_number": "CR Number",
            "vat_number": "VAT Number",
            "company_phone": "Company Official Number",
            "company_email": "Company Email",
            "primary_contact_name": "Primary Contact",
            "mobile": "Mobile Number",
            "email": "Email Address",
            "address": "Address",
            "street_number": "Street Number",
            "postal_code": "Postal Code",
        }

    def __init__(self, *args, company=None, include_materials=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Vendor onboarding is intentionally progressive: operators can save a partial
        # reference record and complete commercial/contact details later. Code/name are
        # normalized in clean() so the model still receives a safe unique identity.
        for name, field in self.fields.items():
            field.required = False
            if name != "materials":
                field.widget.attrs.setdefault("class", "sourcing-input")
        if include_materials:
            if company is None:
                self.fields["materials"].queryset = SourcingMaterial.objects.none()
            else:
                self.fields["materials"].queryset = (
                    SourcingMaterial.objects.for_company(company)
                    .filter(is_active=True)
                    .order_by("category", "name", "code")
                )
            material_field = self.fields["materials"]
            material_field.label_from_instance = lambda material: (
                f"{material.category} · {material.name} · {material.code}"
                if material.category
                else f"{material.name} · {material.code}"
            )
        else:
            self.fields.pop("materials", None)
        self.fields["code"].help_text = "Optional. A unique Vendor code is generated automatically when left blank."
        self.fields["name"].help_text = "Optional. If blank, Display Name is used; if both are blank, a temporary name is generated."
        self.fields["display_name"].help_text = "Optional directory name. If blank, Company / Vendor Name is used."
        self.fields["company_phone"].help_text = "Vendor company switchboard or official business number."
        self.fields["company_email"].help_text = "Vendor company general or official email address."

    def clean(self):
        cleaned = super().clean()
        code = str(cleaned.get("code") or "").strip().upper()
        if not code:
            from .services.vendors import suggest_vendor_code

            code = suggest_vendor_code()
        name = " ".join(str(cleaned.get("name") or "").split())
        display_name = " ".join(str(cleaned.get("display_name") or "").split())
        if not name:
            name = display_name or f"Vendor {code}"
        if not display_name:
            display_name = name
        cleaned["code"] = code
        cleaned["name"] = name
        cleaned["display_name"] = display_name
        return cleaned


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
    category = forms.ChoiceField(
        required=False,
        label="Material Category / Type",
        choices=(),
        widget=forms.Select(attrs={"data-material-category-select": ""}),
    )
    new_category = forms.CharField(
        required=False,
        max_length=120,
        label="New Category / Type",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter a new material category / type",
                "autocomplete": "off",
                "data-new-material-category-input": "",
            }
        ),
        help_text="The new category/type becomes available for later materials as soon as this material is saved.",
    )
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
            "default_unit": forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ..."}),
            "notes": forms.Textarea(attrs={"rows": 4, "placeholder": "Reference notes for this Sourcing Material"}),
        }
        labels = {"default_unit": "Default Unit"}

    def __init__(self, *args, company=None, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        current_category = clean_text(getattr(self.instance, "category", "")) if self.instance else ""
        posted_category = ""
        if self.is_bound:
            posted_category = clean_text(self.data.get(self.add_prefix("category"), ""))
        category_values = list(categories) if categories is not None else sourcing_material_categories(company)
        self.category_values = category_values
        self.fields["category"].choices = _material_category_choices(
            categories=category_values,
            current=current_category,
            posted=posted_category,
        )
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["aliases"] = "\n".join(self.instance.aliases or [])
            self.initial["category"] = current_category
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Independent Sourcing code; it is not an Inventory item code."

    def clean(self):
        cleaned = super().clean()
        category = clean_text(cleaned.get("category"))
        new_category = clean_text(cleaned.get("new_category"))
        if category == NEW_MATERIAL_CATEGORY_VALUE:
            if not new_category:
                self.add_error("new_category", "Enter the new material category / type.")
            else:
                cleaned["category"] = _canonical_material_category(new_category, self.category_values)
        else:
            cleaned["category"] = _canonical_material_category(category, self.category_values)
        return cleaned

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


class SourcingVendorNewMaterialForm(forms.Form):
    """Small material-master form embedded in New Vendor onboarding.

    It deliberately creates the same ``SourcingMaterial`` records as the normal
    Reference > Materials page; there is no vendor-private material vocabulary.
    """

    name = forms.CharField(
        max_length=200,
        label="Material Name",
        widget=forms.TextInput(attrs={"placeholder": "Material / item name", "autocomplete": "off"}),
    )
    category = forms.ChoiceField(
        required=False,
        label="Material Category / Type",
        choices=(),
        widget=forms.Select(attrs={"data-material-category-select": ""}),
    )
    new_category = forms.CharField(
        required=False,
        max_length=120,
        label="New Category / Type",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter a new category / type",
                "autocomplete": "off",
                "data-new-material-category-input": "",
            }
        ),
    )
    default_unit = forms.CharField(
        required=False,
        max_length=40,
        label="Default Unit",
        widget=forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ...", "autocomplete": "off"}),
    )
    code = forms.CharField(
        required=False,
        max_length=40,
        label="Material Code",
        widget=forms.TextInput(attrs={"placeholder": "Auto-generated if blank", "autocomplete": "off"}),
        help_text="Optional. A Sourcing material code is generated automatically when blank.",
    )

    def __init__(self, *args, company=None, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        posted_category = ""
        if self.is_bound:
            posted_category = clean_text(self.data.get(self.add_prefix("category"), ""))
        category_values = list(categories) if categories is not None else sourcing_material_categories(company)
        self.category_values = category_values
        self.fields["category"].choices = _material_category_choices(
            categories=category_values,
            posted=posted_category,
        )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")

    def clean(self):
        cleaned = super().clean()
        name = clean_text(cleaned.get("name"))
        code = clean_text(cleaned.get("code")).upper()
        category = clean_text(cleaned.get("category"))
        new_category = clean_text(cleaned.get("new_category"))
        default_unit = clean_text(cleaned.get("default_unit"))

        if category == NEW_MATERIAL_CATEGORY_VALUE:
            if not new_category:
                self.add_error("new_category", "Enter the new material category / type.")
            else:
                category = _canonical_material_category(new_category, self.category_values)
        else:
            category = _canonical_material_category(category, self.category_values)

        cleaned["name"] = name
        cleaned["code"] = code
        cleaned["category"] = category
        cleaned["default_unit"] = default_unit

        if self.company is not None and name:
            normalized_name = normalize_text(name)
            if SourcingMaterial.objects.for_company(self.company).filter(normalized_name=normalized_name).exists():
                self.add_error("name", "A Sourcing Material with this name already exists. Select it from Existing Materials instead.")
        if self.company is not None and code:
            if SourcingMaterial.objects.for_company(self.company).filter(code__iexact=code).exists():
                self.add_error("code", "A Sourcing Material with this code already exists.")
        return cleaned

    def material_data(self) -> dict[str, object]:
        return {
            "code": clean_text(self.cleaned_data.get("code")).upper(),
            "name": clean_text(self.cleaned_data.get("name")),
            "category": clean_text(self.cleaned_data.get("category")),
            "default_unit": clean_text(self.cleaned_data.get("default_unit")),
            "aliases": [],
            "notes": "",
        }


class BaseSourcingVendorNewMaterialFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        seen_names: set[str] = set()
        seen_codes: set[str] = set()
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if self.can_delete and form.cleaned_data.get("DELETE"):
                continue
            name = normalize_text(form.cleaned_data.get("name"))
            code = clean_text(form.cleaned_data.get("code")).upper()
            if name:
                if name in seen_names:
                    form.add_error("name", "This material is already included in another new-material row.")
                seen_names.add(name)
            if code:
                if code in seen_codes:
                    form.add_error("code", "This material code is already included in another new-material row.")
                seen_codes.add(code)


SourcingVendorNewMaterialFormSet = forms.formset_factory(
    SourcingVendorNewMaterialForm,
    formset=BaseSourcingVendorNewMaterialFormSet,
    extra=1,
    can_delete=True,
    max_num=20,
    validate_max=True,
)


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
