from __future__ import annotations

from django.apps import apps
from django.core.checks import run_checks
from django.core.exceptions import ValidationError
from django.db.utils import NotSupportedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.modules import PlatformModule, membership_can_module, module_from_path, module_home_name
from apps.core.models import AuditArea, Company
from apps.sourcing.isolation import FORBIDDEN_OPERATIONAL_APP_LABELS
from apps.sourcing.models import (
    SourcingManpowerSupplier,
    SourcingMaterial,
    SourcingTrade,
    SourcingVendor,
    SourcingVendorOffer,
    SourcingVendorOfferRevision,
    SourcingWorkforceOffer,
    SourcingWorkforceOfferRevision,
)


class SourcingDomainFoundationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="SESCCO", slug="sescco-sourcing-test")
        self.other_company = Company.objects.create(name="Other", slug="other-sourcing-test")

    def test_sourcing_models_have_no_operational_relations(self):
        config = apps.get_app_config("sourcing")
        for model in config.get_models():
            for field in model._meta.get_fields():
                remote_model = getattr(getattr(field, "remote_field", None), "model", None)
                remote_meta = getattr(remote_model, "_meta", None)
                if remote_meta is not None:
                    self.assertNotIn(remote_meta.app_label, FORBIDDEN_OPERATIONAL_APP_LABELS)
        self.assertFalse([error for error in run_checks(tags=["models"]) if error.id.startswith("sourcing.E")])

    def test_vendor_offer_rejects_cross_company_vendor_or_material(self):
        vendor = SourcingVendor.objects.create(company=self.company, code="V-001", name="Vendor One")
        other_material = SourcingMaterial.objects.create(
            company=self.other_company, code="MAT-001", name="Rebar", default_unit="ton"
        )
        offer = SourcingVendorOffer(
            company=self.company,
            vendor=vendor,
            material=other_material,
            available_quantity=10,
            rate=2200,
        )
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_workforce_offer_rejects_cross_company_supplier_or_trade(self):
        supplier = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MP-001", name="Reference Manpower"
        )
        trade = SourcingTrade.objects.create(
            company=self.other_company, code="TR-001", name="Steel Fixer"
        )
        offer = SourcingWorkforceOffer(company=self.company, supplier=supplier, trade=trade, rate=2200)
        with self.assertRaises(ValidationError):
            offer.full_clean()

    def test_vendor_offer_revision_is_immutable(self):
        vendor = SourcingVendor.objects.create(company=self.company, code="V-002", name="Vendor Two")
        material = SourcingMaterial.objects.create(company=self.company, code="MAT-002", name="Cement")
        offer = SourcingVendorOffer.objects.create(company=self.company, vendor=vendor, material=material)
        revision = SourcingVendorOfferRevision.objects.create(
            company=self.company,
            offer=offer,
            verified_at=timezone.now(),
            before={},
            after={"availableQuantity": "100"},
        )
        revision.note = "rewrite"
        with self.assertRaises(ValidationError):
            revision.save()
        with self.assertRaises(ValidationError):
            revision.delete()
        with self.assertRaises(NotSupportedError):
            SourcingVendorOfferRevision.objects.filter(pk=revision.pk).update(note="rewrite")
        with self.assertRaises(NotSupportedError):
            SourcingVendorOfferRevision.objects.filter(pk=revision.pk).delete()

    def test_workforce_revision_is_immutable(self):
        supplier = SourcingManpowerSupplier.objects.create(
            company=self.company, code="MP-002", name="Reference Manpower Two"
        )
        trade = SourcingTrade.objects.create(company=self.company, code="TR-002", name="Electrician")
        offer = SourcingWorkforceOffer.objects.create(company=self.company, supplier=supplier, trade=trade)
        revision = SourcingWorkforceOfferRevision.objects.create(
            company=self.company,
            offer=offer,
            verified_at=timezone.now(),
            before={},
            after={"availableQuantity": 12},
        )
        with self.assertRaises(NotSupportedError):
            SourcingWorkforceOfferRevision.objects.filter(pk=revision.pk).update(note="rewrite")

    def test_sourcing_audit_area_and_module_are_registered_and_anonymous_access_fails_closed(self):
        self.assertEqual(AuditArea.SOURCING, "sourcing")
        self.assertEqual(module_from_path("/app/sourcing/"), PlatformModule.SOURCING)
        self.assertEqual(module_home_name(PlatformModule.SOURCING), "sourcing:home")
        self.assertFalse(membership_can_module(None, PlatformModule.SOURCING))
