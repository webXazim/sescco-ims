"""Draft-only capability formsets for new Manpower and Subcontractor profiles.

No uncontrolled master records are created until the parent form and every offer
have validated. Existing master ModelForms provide the authoritative validation.
"""
from __future__ import annotations

from copy import deepcopy

from django import forms
from django.core.exceptions import ValidationError

from .forms import (SourcingWorkforceOfferForm, SourcingSubcontractorServiceForm,
                    SourcingTradeForm, SourcingServiceForm)
from .models import SourcingTrade, SourcingService
from .models.base import clean_text, normalize_text
from .services.workforce import suggest_trade_code


class DraftCapabilityMixin:
    master_model = None
    master_form = None
    master_field = ''
    master_fields = ()

    def __init__(self, *args, can_create_master=False, categories=None, **kwargs):
        self.master_company = kwargs.get('company')
        self.can_create_master = can_create_master
        self.staged_categories = categories
        super().__init__(*args, **kwargs)
        self.fields[self.master_field].required = False
        for name in self.master_fields:
            new_field = deepcopy(self.master_form.base_fields[name])
            new_field.required = False
            new_field.widget.attrs.setdefault('class', 'sourcing-input')
            # The parent form's existing category is a free-text/choice control.
            if name == 'category' and self.master_field == 'service':
                from .selectors.services_master import service_categories
                from .forms import _material_category_choices
                new_field.choices = _material_category_choices(
                    categories=self.staged_categories if self.staged_categories is not None
                    else service_categories(self.master_company)
                )
                new_field.widget.attrs['data-material-category-select'] = ''
            if name == 'new_category':
                new_field.widget.attrs['data-new-material-category-input'] = ''
            self.fields[f'new_master_{name}'] = new_field
        if not self.is_bound:
            self.initial['verified_now'] = False

    def clean(self):
        data = super().clean()
        if data.get('DELETE'):
            return data
        master_data = {name: data.get(f'new_master_{name}') or '' for name in self.master_fields}
        wants_new = any(clean_text(str(master_data.get(name) or '')) for name in
                        ('code', 'name', 'category', 'new_category', 'aliases', 'description', 'notes')
                        if name in master_data)
        if wants_new:
            if not self.can_create_master:
                self.add_error('new_master_name', 'Reference Masters edit permission is required.')
            if data.get(self.master_field):
                self.add_error(self.master_field, 'Choose an existing reference OR create a new one.')
            if not clean_text(master_data['code']) and self.master_field == 'trade':
                master_data['code'] = suggest_trade_code()
            if not clean_text(master_data['name']):
                self.add_error('new_master_name', 'Enter the new reference name.')
            if self.master_company is not None:
                name = normalize_text(master_data['name'])
                qs = self.master_model.objects.for_company(self.master_company)
                if name and qs.filter(normalized_name=name).exists():
                    self.add_error('new_master_name', 'This reference already exists. Search and select it.')
                if master_data['code'] and qs.filter(code__iexact=master_data['code']).exists():
                    self.add_error('new_master_code', 'This reference code already exists.')
            if self.master_field == 'service':
                master_form = self.master_form(
                    data=master_data, company=self.master_company, categories=self.staged_categories
                )
            else:
                master_form = self.master_form(data=master_data)
            if not master_form.is_valid():
                for name, errors in master_form.errors.items():
                    target = f'new_master_{name}'
                    for error in errors:
                        self.add_error(target if target in self.fields else None, error)
            else:
                data['draft_master'] = {key: master_form.cleaned_data[key]
                                        for key in self.master_form.Meta.fields}
        elif not data.get(self.master_field):
            self.add_error(self.master_field, 'Select an existing reference or create a new one.')
        return data

    def offer_data(self):
        return {name: self.cleaned_data.get(name) for name in self.Meta.fields
                if name != self.master_field}


class SourcingManpowerOnboardingForm(DraftCapabilityMixin, SourcingWorkforceOfferForm):
    master_model = SourcingTrade
    master_form = SourcingTradeForm
    master_field = 'trade'
    master_fields = ('code', 'name', 'category', 'aliases', 'notes')


class SourcingSubcontractorOnboardingForm(DraftCapabilityMixin, SourcingSubcontractorServiceForm):
    master_model = SourcingService
    master_form = SourcingServiceForm
    master_field = 'service'
    master_fields = ('code', 'name', 'category', 'new_category', 'default_rate_basis',
                     'description', 'aliases', 'notes')


class BaseCapabilityOnboardingFormSet(forms.BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        names, codes, entries = set(), set(), set()
        for form in self.forms:
            data = getattr(form, 'cleaned_data', None)
            if not data or data.get('DELETE'):
                continue
            draft = data.get('draft_master')
            if draft:
                name = normalize_text(draft['name'])
                code = clean_text(draft['code']).casefold()
                if name in names:
                    form.add_error('new_master_name', 'The same new reference was added twice.')
                if code in codes:
                    form.add_error('new_master_code', 'The same reference code was added twice.')
                names.add(name)
                codes.add(code)
                identity = ('new', name)
            else:
                existing = data.get(form.master_field)
                identity = ('existing', str(existing.pk)) if existing else ('invalid', '')
            detail = (normalize_text(data.get('scope_description')) if form.master_field == 'service'
                      else normalize_text(data.get('work_location')))
            key = (identity, detail)
            if key in entries:
                form.add_error(None, 'This capability is already listed; edit that row instead.')
            entries.add(key)


SourcingManpowerOnboardingFormSet = forms.formset_factory(
    SourcingManpowerOnboardingForm, formset=BaseCapabilityOnboardingFormSet,
    extra=0, can_delete=True, max_num=50, absolute_max=100, validate_max=True)
SourcingSubcontractorOnboardingFormSet = forms.formset_factory(
    SourcingSubcontractorOnboardingForm, formset=BaseCapabilityOnboardingFormSet,
    extra=0, can_delete=True, max_num=50, absolute_max=100, validate_max=True)
