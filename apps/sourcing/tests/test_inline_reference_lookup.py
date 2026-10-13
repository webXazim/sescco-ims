"""Regression tests for bounded searchable reference selectors and inline master creation."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import AccessProfile, AccessProfilePermission, CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.sourcing.forms import (
    SourcingVendorOfferForm, SourcingWorkforceOfferForm, SourcingSubcontractorServiceForm,
)
from apps.sourcing.models import (
    SourcingMaterial, SourcingTrade, SourcingService, SourcingVendorOffer,
    SourcingVendor, SourcingManpowerSupplier, SourcingSubcontractor,
)
from apps.sourcing.tests.support import SOURCING_HTTP_TEST_STORAGES


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES=SOURCING_HTTP_TEST_STORAGES)
class InlineReferenceLookupTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Lookup tenant", slug="lookup-tenant")
        self.other = Company.objects.create(name="Other lookup tenant", slug="other-lookup-tenant")
        self.user = get_user_model().objects.create_user(username="reference-owner", password="test-password")
        CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.client.force_login(self.user)
        self.material = SourcingMaterial.objects.create(
            company=self.company, code="MAT-ONE", name="Safety Helmet", category="Safety", aliases=["Hard Hat"],
        )
        self.trade = SourcingTrade.objects.create(
            company=self.company, code="TRD-ONE", name="Electrician", category="Electrical", aliases=["Wireman"],
        )
        self.service = SourcingService.objects.create(
            company=self.company, code="SRV-ONE", name="Calibration", category="Testing", aliases=["Calibrate tools"],
        )
        self.remote = SourcingMaterial.objects.create(company=self.other, code="MAT-SECRET", name="Secret material")
        self.vendor = SourcingVendor.objects.create(company=self.company, code="VND-ONE", name="Vendor One")
        self.supplier = SourcingManpowerSupplier.objects.create(company=self.company, code="MPS-ONE", name="Manpower One")
        self.subcontractor = SourcingSubcontractor.objects.create(company=self.company, code="SUB-ONE", name="Service One")

    def lookup(self, kind, params=None):
        return self.client.get(reverse('sourcing:reference_lookup', args=[kind]), params or {})

    def test_default_items_show_even_before_search_and_cap_results(self):
        SourcingVendorOffer.objects.create(company=self.company, vendor=self.vendor, material=self.material)
        SourcingMaterial.objects.bulk_create([
            SourcingMaterial(company=self.company, code=f'MAT-{i:03d}', name=f'Sample Item {i}', normalized_name=f'sample item {i}')
            for i in range(35)
        ])
        response = self.lookup('material')
        self.assertEqual(response.status_code, 200)
        entries = response.json()['results']
        self.assertLessEqual(len(entries), 12)
        self.assertEqual(entries[0]['id'], str(self.material.pk))
        self.assertNotIn(str(self.remote.pk), [entry['id'] for entry in entries])
        self.assertEqual(self.lookup('material', {'q': 'MAT-SECRET'}).json()['results'], [])
        self.assertEqual(self.lookup('material', {'q': 'Hard Hat'}).json()['results'][0]['id'], str(self.material.pk))

    def test_trade_service_aliases_company_scope_and_inactive_filter(self):
        self.assertEqual(self.lookup('trade', {'q': 'wireman'}).json()['results'][0]['id'], str(self.trade.pk))
        self.assertEqual(self.lookup('service', {'q': 'calibrate tools'}).json()['results'][0]['id'], str(self.service.pk))
        self.service.is_active = False
        self.service.save(update_fields=['is_active', 'updated_at'])
        self.assertEqual(self.lookup('service', {'q': 'calibration'}).json()['results'], [])
        self.assertEqual(self.lookup('service', {'selected': str(self.service.pk)}).json()['results'][0]['id'], str(self.service.pk))
        self.assertEqual(self.lookup('material', {'selected': str(self.remote.pk)}).json()['results'], [])
        self.assertEqual(self.lookup('material', {'selected': 'not-a-uuid'}).json()['results'], [])

    def test_forms_validate_all_active_company_items_without_rendering_big_selects(self):
        for cls, key, obj in (
            (SourcingVendorOfferForm, 'material', self.material),
            (SourcingWorkforceOfferForm, 'trade', self.trade),
            (SourcingSubcontractorServiceForm, 'service', self.service),
        ):
            form = cls(company=self.company)
            rendered = str(form[key])
            self.assertIn('type="hidden"', rendered)
            self.assertNotIn('<option', rendered)
            self.assertEqual(form.fields[key].clean(str(obj.pk)), obj)
        with self.assertRaises(ValidationError):
            SourcingVendorOfferForm(company=self.company).fields['material'].clean(str(self.remote.pk))

    def test_inline_creation_uses_standard_audit_services(self):
        for kind, name, payload, model, action in (
            ('material', 'Electrical Switchgear', {'category': 'Electrical', 'default_unit': 'pcs'}, SourcingMaterial, 'sourcing.material.created'),
            ('trade', 'HVAC Inspector', {'category': 'HVAC'}, SourcingTrade, 'sourcing.trade.created'),
            ('service', 'High Voltage Testing', {'category': 'Testing'}, SourcingService, 'sourcing.service.created'),
        ):
            response = self.client.post(reverse('sourcing:reference_lookup', args=[kind]), {'name': name, **payload})
            self.assertEqual(response.status_code, 201, response.content)
            saved = model.objects.get(pk=response.json()['item']['id'], company=self.company)
            self.assertEqual(saved.name, name)
            self.assertTrue(AuditEvent.objects.filter(company=self.company, area=AuditArea.SOURCING, object_id=saved.pk, action=action).exists())
            self.assertEqual(self.lookup(kind, {'selected': str(saved.pk)}).status_code, 200)

    def test_invalid_duplicates_and_get_do_not_create(self):
        self.assertEqual(self.client.post(reverse('sourcing:reference_lookup', args=['material']), {'name': ''}).status_code, 400)
        self.assertEqual(self.client.post(reverse('sourcing:reference_lookup', args=['material']), {'name': 'Safety Helmet'}).status_code, 400)
        self.assertEqual(self.client.get(reverse('sourcing:reference_lookup', args=['invalid'])).status_code, 404)
        self.assertEqual(self.lookup('material', {'q': 'Safety Helmet'}).status_code, 200)

    def test_master_creation_permission_is_separate_from_vendor_edit_permission(self):
        reader = get_user_model().objects.create_user(username='lookup-vendor-editor', password='test-password')
        profile = AccessProfile.objects.create(company=self.company, key='reference-vendor-editor', name='Vendor Editor', is_system=False, is_active=True)
        AccessProfilePermission.objects.create(profile=profile, permission=AccessPermission.SOURCING_VENDORS_MANAGE.value)
        CompanyMembership.objects.create(company=self.company, user=reader, role=AccessRole.CUSTOM, access_profile=profile)
        self.client.force_login(reader)
        self.assertEqual(self.lookup('material').status_code, 200)
        resp = self.client.post(reverse('sourcing:reference_lookup', args=['material']), {'name': 'Unauthorized Material'})
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(SourcingMaterial.objects.filter(company=self.company, name='Unauthorized Material').exists())

    def test_offer_forms_use_shared_lookup_and_stay_on_the_current_page(self):
        checks = [
            ('vendor_offer_create', [self.vendor.pk], 'material'),
            ('workforce_offer_create', [self.supplier.pk], 'trade'),
            ('subcontractor_service_create', [self.subcontractor.pk], 'service'),
        ]
        for view, args, kind in checks:
            response = self.client.get(reverse('sourcing:' + view, args=args))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'data-sourcing-reference-lookup')
            self.assertContains(response, reverse('sourcing:reference_lookup', args=[kind]))
            self.assertContains(response, 'data-reference-add')
