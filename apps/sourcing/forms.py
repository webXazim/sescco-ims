from __future__ import annotations

from django import forms
from django.db.models import Q

from .models import (
    SourcingAvailability,
    SourcingMaterial,
    SourcingService,
    SourcingManpowerSupplier,
    SourcingManpowerContact,
    SourcingRateBasis,
    SourcingTrade,
    SourcingWorkforceOffer,
    SourcingVendor,
    SourcingVendorContact,
    SourcingVendorOffer,
    SourcingSubcontractor,
    SourcingSubcontractorContact,
    SourcingSubcontractorService,
)
from .models.subcontractors import SourcingSubcontractorDocument
from .models.base import clean_text, normalize_text


from .models.provider_tags import normalize_provider_tags


class SourcingProviderTagsFormMixin:
    """Field normalization shared by all three concrete Django ModelForms."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["tags"] = ", ".join(self.instance.tags or [])

    def clean_tags(self):
        value = self.cleaned_data.get("tags", "")
        if len(value) > 430:
            raise forms.ValidationError("Tags are too long.")
        try:
            return normalize_provider_tags(value.split(","))
        except ValidationError as error:
            raise forms.ValidationError(error.messages) from error


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


class SourcingVendorForm(SourcingProviderTagsFormMixin, forms.ModelForm):
    tags = forms.CharField(
        required=False, label="Company tags",
        widget=forms.TextInput(attrs={"class": "sourcing-input", "placeholder": "Electrical, Civil", "list": "sourcing-provider-tags", "data-provider-tag-field": "1"}),
        help_text="Type a tag and press Enter to add it. Add up to 10 tags; remove tags with ×. These classify the company, not its individual capabilities.",
    )

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
            "tags",
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
        self._vendor_company = company
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
        self.fields["code"].help_text = "Optional. Leave blank for a readable VND code based on the company name; repeated prefixes receive a numeric suffix."
        self.fields["name"].help_text = "Optional. If blank, Display Name is used; if both are blank, a temporary name is generated."
        self.fields["display_name"].help_text = "Optional directory name. If blank, Company / Vendor Name is used."
        self.fields["company_phone"].help_text = "Vendor company switchboard or official business number."
        self.fields["company_email"].help_text = "Vendor company general or official email address."

    def clean(self):
        cleaned = super().clean()
        code = str(cleaned.get("code") or "").strip().upper()
        name = " ".join(str(cleaned.get("name") or "").split())
        display_name = " ".join(str(cleaned.get("display_name") or "").split())
        if not code:
            from .services.vendors import suggest_vendor_code
            code = suggest_vendor_code(name=name or display_name, company=self._vendor_company)
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


class SourcingManpowerSupplierForm(SourcingProviderTagsFormMixin, forms.ModelForm):
    tags = forms.CharField(
        required=False, label="Company tags",
        widget=forms.TextInput(attrs={"class": "sourcing-input", "placeholder": "Electrical, Civil", "list": "sourcing-provider-tags", "data-provider-tag-field": "1"}),
        help_text="Type a tag and press Enter to add it. Add up to 10 tags; remove tags with ×. These classify the company, not its individual capabilities.",
    )

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
            "tags",
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

    def __init__(self, *args, company=None, **kwargs):
        self._company = company
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].required = False
        self.fields["code"].help_text = "Optional. Generated from the supplier name if blank."

    def clean(self):
        data = super().clean()
        if not clean_text(data.get("code")):
            from .services.manpower import suggest_manpower_supplier_code
            data["code"] = suggest_manpower_supplier_code(
                name=data.get("name", ""), company=self._company)
        return data


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
        # The selection is resolved by the bounded AJAX lookup, not a giant HTML select.
        # ModelChoiceField still validates a submitted UUID against the entire company-scoped queryset.
        self.fields["trade"].widget = forms.HiddenInput()
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
        # The selection is resolved by the bounded AJAX lookup, not a giant HTML select.
        # ModelChoiceField still validates a submitted UUID against the entire company-scoped queryset.
        self.fields["material"].widget = forms.HiddenInput()
        self.fields["material"].help_text = "Materials are managed in the independent Sourcing reference master."
        self.fields["available_quantity"].help_text = "Leave blank when the Vendor did not confirm quantity."
        self.fields["rate"].help_text = "Reference quote only. It never posts to Inventory or Accounting."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if not (self.instance and self.instance.pk):
                self.initial["verified_now"] = True


class SourcingVendorOnboardingOfferForm(SourcingVendorOfferForm):
    """A complete supply offer before the parent Vendor exists.

    Offers use the very same ModelForm fields and model validation as Add Supply
    Item.  A new controlled Material may be drafted alongside the offer, and is
    only persisted once the entire Vendor formset validates and saves atomically.
    """

    # These are optional on the parent offer, since an existing Material may be
    # selected instead. The nested editor validates the name/category when used,
    # then SourcingMaterialForm validates the full draft during Vendor save.
    new_material_code = forms.CharField(
        required=False, max_length=40, label="Code",
        widget=forms.TextInput(attrs={"placeholder": "Auto-generated if blank", "autocomplete": "off"}),
        help_text="Independent Sourcing code; not an Inventory item code. Auto-generated if blank.",
    )
    new_material_name = forms.CharField(
        required=False, max_length=200, label="Name",
        widget=forms.TextInput(attrs={"placeholder": "Material / item name", "autocomplete": "off"}),
    )
    new_material_category = forms.ChoiceField(required=False, choices=(), label="Material Category / Type")
    new_material_new_category = forms.CharField(
        required=False, max_length=120, label="New Category / Type",
        widget=forms.TextInput(attrs={"placeholder": "Enter a new material category / type"}),
        help_text="The new category/type becomes available for later materials when this Vendor is saved.",
    )
    new_material_default_unit = forms.CharField(
        required=False, max_length=40, label="Default Unit",
        widget=forms.TextInput(attrs={"placeholder": "pcs, box, kg, m, ton ..."}),
    )
    new_material_aliases = forms.CharField(
        required=False, label="Aliases",
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "One alias per line, e.g.\nReinforcement Bar\nSteel Bar"}),
        help_text="Optional search aliases. One alias per line or comma-separated.",
    )
    new_material_notes = forms.CharField(
        required=False, label="Notes", widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Reference notes for this Sourcing Material"}),
    )

    def __init__(self, *args, can_create_materials=False, categories=None, **kwargs):
        self.company = kwargs.get("company")
        super().__init__(*args, **kwargs)
        self.can_create_materials = can_create_materials
        self.categories = categories or ()
        self.fields["material"].required = False
        self.fields["new_material_category"].choices = _material_category_choices(
            categories=categories or (),
            posted=clean_text(self.data.get(self.add_prefix("new_material_category"), "")) if self.is_bound else "",
        )
        self.fields["new_material_category"].widget.attrs["data-material-category-select"] = ""
        self.fields["new_material_new_category"].widget.attrs["data-new-material-category-input"] = ""
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        if not self.is_bound:
            # Nothing is verified merely because the user adds a draft capability.
            self.initial["verified_now"] = False

    def clean(self):
        cleaned = super().clean()
        # Deleted rows are disregarded by Django's formset after field validation.
        if cleaned.get("DELETE"):
            return cleaned
        new_fields = ("code", "name", "category", "new_category", "default_unit", "aliases", "notes")
        new_values = {
            field: cleaned.get(f"new_material_{field}") or ""
            for field in new_fields
        }
        wants_new = any(clean_text(value) for value in new_values.values())
        if wants_new:
            chosen_category = clean_text(new_values["category"])
            if chosen_category and chosen_category != NEW_MATERIAL_CATEGORY_VALUE and not any(
                clean_text(allowed).casefold() == chosen_category.casefold()
                for allowed in self.categories
            ):
                self.add_error("new_material_category", "Choose an existing or staged category, or add a new one.")
            if not self.can_create_materials:
                self.add_error("new_material_name", "Reference Masters edit access is required to create a new material.")
            if cleaned.get("material"):
                self.add_error("material", "Choose an existing material OR create a new material, not both.")
            # The full standalone ModelForm requires a code; generate it here,
            # exactly as the dedicated reference-master creation service does.
            if not clean_text(new_values["code"]):
                from .services.catalog import suggest_material_code
                new_values["code"] = suggest_material_code()
            if self.company is not None:
                name = normalize_text(new_values["name"])
                if name and SourcingMaterial.objects.for_company(self.company).filter(normalized_name=name).exists():
                    self.add_error("new_material_name", "This material already exists. Search and select it instead.")
                if SourcingMaterial.objects.for_company(self.company).filter(code__iexact=new_values["code"]).exists():
                    self.add_error("new_material_code", "This material code already exists.")
            # Reuse the full standalone master form's model/category/alias validation.
            master = SourcingMaterialForm(data=new_values, company=self.company, categories=self.categories)
            if not master.is_valid():
                for name, errors in master.errors.items():
                    target = f"new_material_{name}"
                    for error in errors:
                        if target in self.fields:
                            self.add_error(target, error)
                        else:
                            self.add_error(None, error)
            else:
                cleaned["draft_material"] = {
                    key: master.cleaned_data[key]
                    for key in ("code", "name", "category", "default_unit", "aliases", "notes")
                }
        elif not cleaned.get("material"):
            self.add_error("material", "Select a material or create a new one.")
        return cleaned

    def offer_data(self):
        keys = SourcingVendorOfferForm.Meta.fields
        return {key: self.cleaned_data.get(key) for key in keys if key != "material"}


class BaseSourcingVendorOnboardingOfferFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        new_names = set()
        new_codes = set()
        identities = set()
        for form in self.forms:
            data = getattr(form, "cleaned_data", None)
            if not data or data.get("DELETE"):
                continue
            draft = data.get("draft_material")
            if draft:
                name = normalize_text(draft["name"])
                code = clean_text(draft["code"]).upper()
                if name in new_names:
                    form.add_error("new_material_name", "This material is already created in another supply item.")
                new_names.add(name)
                if code and code in new_codes:
                    form.add_error("new_material_code", "This material code is already used in another supply item.")
                if code:
                    new_codes.add(code)
                identity_material = ("new", name)
            else:
                material = data.get("material")
                identity_material = ("existing", str(material.pk)) if material else ("invalid", "")
            identity = (
                identity_material,
                normalize_text(data.get("specification")),
                normalize_text(data.get("brand")),
                normalize_text(data.get("model")),
            )
            if identity in identities:
                form.add_error("specification", "This supply item has already been added. Edit the existing row instead.")
            identities.add(identity)


SourcingVendorOnboardingOfferFormSet = forms.formset_factory(
    SourcingVendorOnboardingOfferForm,
    formset=BaseSourcingVendorOnboardingOfferFormSet,
    extra=0,
    can_delete=True,
    max_num=50,
    absolute_max=100,
    validate_max=True,
)


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


class SourcingServiceForm(forms.ModelForm):
    """Controlled company service vocabulary; not an operational service job."""

    code = forms.CharField(required=False, max_length=40, label="Service Code")
    category = forms.ChoiceField(
        required=False, label="Service Category", choices=(),
        widget=forms.Select(attrs={"data-material-category-select": ""}),
    )
    new_category = forms.CharField(
        required=False, max_length=120, label="New Service Category",
        widget=forms.TextInput(attrs={
            "placeholder": "Enter a new service category",
            "autocomplete": "off", "data-new-material-category-input": "",
        }),
    )
    aliases = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "One search alias per line"}),
        help_text="Alternative terms or abbreviations. Use one per line or comma-separated.",
    )

    class Meta:
        model = SourcingService
        fields = ("code", "name", "category", "default_rate_basis", "aliases", "description", "notes")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. HVAC installation", "autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Define what this service covers"}),
            "notes": forms.Textarea(attrs={"rows": 3, "placeholder": "Internal sourcing reference notes"}),
        }
        labels = {"default_rate_basis": "Default Rate Basis"}

    def __init__(self, *args, company=None, categories=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .selectors.services_master import service_categories
        self.company = company
        choices = list(categories) if categories is not None else (service_categories(company) if company else [])
        self.category_values = choices
        current = clean_text(self.instance.category) if self.instance and self.instance.pk else ""
        posted = clean_text(self.data.get(self.add_prefix("category"))) if self.is_bound else ""
        self.fields["category"].choices = _material_category_choices(
            categories=choices, current=current, posted=posted
        )
        if self.instance and self.instance.pk and not self.is_bound:
            self.initial["aliases"] = "\n".join(self.instance.aliases or [])
            self.initial["category"] = current
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].help_text = "Independent Sourcing Services code, not an Inventory reference. Auto-generated if empty."

    def clean_aliases(self):
        raw = str(self.cleaned_data.get("aliases") or "")
        aliases, seen = [], set()
        for chunk in raw.replace(",", "\n").splitlines():
            alias = clean_text(chunk)
            key = normalize_text(alias)
            if alias and key not in seen:
                aliases.append(alias)
                seen.add(key)
        return aliases

    def clean(self):
        cleaned = super().clean()
        category = clean_text(cleaned.get("category"))
        if category == NEW_MATERIAL_CATEGORY_VALUE:
            candidate = clean_text(cleaned.get("new_category"))
            if not candidate:
                self.add_error("new_category", "Enter the new service category.")
            category = candidate
        cleaned["category"] = _canonical_material_category(category, self.category_values)
        if not clean_text(cleaned.get("code")):
            from .services.services_master import suggest_service_code
            cleaned["code"] = suggest_service_code()
        else:
            cleaned["code"] = clean_text(cleaned["code"]).upper()
        return cleaned


class SourcingSubcontractorForm(SourcingProviderTagsFormMixin, forms.ModelForm):
    """Company-scoped reference profile; no operational relations."""
    tags = forms.CharField(
        required=False, label="Company tags",
        widget=forms.TextInput(attrs={"class": "sourcing-input", "placeholder": "Electrical, Civil", "list": "sourcing-provider-tags", "data-provider-tag-field": "1"}),
        help_text="Type a tag and press Enter to add it. Add up to 10 tags; remove tags with ×. These classify the company, not its individual capabilities.",
    )

    class Meta:
        model = SourcingSubcontractor
        fields = (
            "code", "name", "display_name", "cr_number", "vat_number",
            "company_phone", "company_email", "website", "primary_contact_name",
            "mobile", "email", "address", "street_number", "district",
            "city", "region", "postal_code", "service_coverage", "tags", "notes",
        )
        widgets = {
            "code": forms.TextInput(attrs={"placeholder": "SUB-XXXXXXXX"}),
            "name": forms.TextInput(attrs={"placeholder": "Legal company name"}),
            "display_name": forms.TextInput(attrs={"placeholder": "Display name"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, company=None, **kwargs):
        self._company = company
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["code"].required = False
        self.fields["display_name"].required = False
        self.fields["code"].help_text = "Optional. Generated from the company name if blank."

    def clean(self):
        result = super().clean()
        if not result.get("code"):
            from .services.subcontractors import suggest_subcontractor_code
            result["code"] = suggest_subcontractor_code(name=result.get("name", ""), company=self._company)
        if not result.get("display_name") and result.get("name"):
            result["display_name"] = result["name"]
        return result


class SourcingSubcontractorContactForm(forms.ModelForm):
    class Meta:
        model = SourcingSubcontractorContact
        fields = (
            "salutation", "first_name", "last_name", "designation", "department",
            "email", "work_phone", "mobile", "is_primary", "is_active",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name not in {"is_primary", "is_active"}:
                field.widget.attrs.setdefault("class", "sourcing-input")


class SourcingSubcontractorServiceForm(forms.ModelForm):
    """Reference-only service offering, scoped to controlled Services master."""
    verified_now = forms.BooleanField(
        required=False, label="Verified now",
        help_text="Only check this when the subcontractor confirmed the service reference now.",
    )
    contact_name = forms.CharField(required=False, max_length=160, label="Spoke With")

    class Meta:
        model = SourcingSubcontractorService
        fields = (
            "service", "scope_description", "service_location", "availability",
            "rate", "currency", "rate_basis", "rate_valid_until", "lead_time",
            "verification_note", "notes",
        )
        widgets = {
            "scope_description": forms.TextInput(attrs={"placeholder": "Scope, deliverables, standards or equipment"}),
            "service_location": forms.TextInput(attrs={"placeholder": "City, region, site or nationwide"}),
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank if not quoted"}),
            "currency": forms.TextInput(attrs={"maxlength": "3", "placeholder": "SAR"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "lead_time": forms.TextInput(attrs={"placeholder": "Mobilization time, e.g. 2 weeks"}),
            "verification_note": forms.TextInput(attrs={"placeholder": "How/when the service reference was confirmed"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "service": "Service Type", "scope_description": "Scope / Specification",
            "service_location": "Service Location", "rate": "Reference Rate",
            "rate_valid_until": "Rate Valid Until", "lead_time": "Mobilization / Lead Time",
        }

    def __init__(self, *args, company=None, subcontractor=None, **kwargs):
        super().__init__(*args, **kwargs)
        queryset = SourcingService.objects.none()
        if company is not None:
            queryset = SourcingService.objects.for_company(company)
            current_id = self.instance.service_id if self.instance and self.instance.pk else None
            queryset = queryset.filter(Q(is_active=True) | Q(pk=current_id)) if current_id else queryset.filter(is_active=True)
        self.fields["service"].queryset = queryset.order_by("category", "normalized_name", "code")
        self.fields["service"].empty_label = "Select Service"
        # The selection is resolved by the bounded AJAX lookup, not a giant HTML select.
        # ModelChoiceField still validates a submitted UUID against the entire company-scoped queryset.
        self.fields["service"].widget = forms.HiddenInput()
        self.fields["service"].help_text = "Select from Reference → Services; service creation requires master-data permission."
        self.fields["rate"].help_text = "Quotation/reference only; not a purchase order, approved contract or accounting entry."
        for name, field in self.fields.items():
            if name not in {"verified_now"}:
                field.widget.attrs.setdefault("class", "sourcing-input")
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if not (self.instance and self.instance.pk):
                self.initial["verified_now"] = False
                if subcontractor is not None:
                    self.initial["service_location"] = subcontractor.city or ""
            if self.instance and self.instance.pk and self.instance.service_id:
                self.initial.setdefault("rate_basis", self.instance.rate_basis)


class SourcingSubcontractorServiceVerifyForm(forms.ModelForm):
    contact_name = forms.CharField(required=False, max_length=160, label="Spoke With")

    class Meta:
        model = SourcingSubcontractorService
        fields = (
            "availability", "rate", "currency", "rate_basis", "rate_valid_until",
            "lead_time", "verification_note",
        )
        widgets = {
            "rate": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "placeholder": "Blank = not quoted"}),
            "rate_valid_until": forms.DateInput(attrs={"type": "date"}),
            "verification_note": forms.TextInput(attrs={"placeholder": "What the subcontractor confirmed"}),
        }

    def __init__(self, *args, subcontractor=None, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "sourcing-input")
        self.fields["rate"].help_text = "Reference quotation only. No transaction or purchase is generated."
        if not self.is_bound:
            self.initial.setdefault("currency", getattr(self.instance, "currency", None) or "SAR")
            if subcontractor is not None:
                self.initial.setdefault("contact_name", subcontractor.primary_contact_name or "")


class SourcingSubcontractorVerificationForm(forms.Form):
    """A company identity check does not verify individual service rates."""
    contact_name = forms.CharField(max_length=160, label="Person contacted")
    note = forms.CharField(max_length=500, label="Verification details", widget=forms.Textarea(attrs={"rows": 4}))
    confirmed = forms.BooleanField(label="I confirmed the subcontractor company details", required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "sourcing-input")


class SourcingSubcontractorDocumentForm(forms.ModelForm):
    upload = forms.FileField(required=False, label="Qualification file (PDF, PNG or JPEG, 10 MB maximum)")

    class Meta:
        model = SourcingSubcontractorDocument
        fields = ("kind", "title", "reference_number", "issuer", "issued_on", "expires_on", "notes")
        widgets = {
            "issued_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "expires_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["upload"].required = not bool(self.instance and self.instance.pk)

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload:
            from .services.subcontractor_documents import inspect_upload
            try:
                inspect_upload(upload)
            except forms.ValidationError as exc:
                # Field cleaners must raise a message list, rather than the
                # service's dictionary of errors keyed by field name.
                raise forms.ValidationError(exc.messages) from exc
        return upload
