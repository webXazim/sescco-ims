"""Upgrade 01 isolation, normalization, permissions, and revision evidence tests."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.utils import NotSupportedError
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Company
from apps.sourcing.models import (
    SourcingSubcontractor, SourcingSubcontractorContact, SourcingService,
    SourcingSubcontractorService, SourcingSubcontractorServiceRevision,
)


class SubcontractorFoundationTests(TestCase):
    def setUp(self):
        self.one = Company.objects.create(name="Subcontractor Co One", slug="subco-found-one")
        self.two = Company.objects.create(name="Subcontractor Co Two", slug="subco-found-two")

    def test_name_normalization_and_company_scoping(self):
        subco = SourcingSubcontractor.objects.create(company=self.one, code=" sc-01 ", name="  HVAC   Services  ")
        self.assertEqual(subco.code, "SC-01")
        self.assertEqual(subco.normalized_name, "hvac services")
        with self.assertRaises(ValidationError):
            SourcingSubcontractor.objects.create(company=self.one, code="SC-02", name="hvac services")
        SourcingSubcontractor.objects.create(company=self.two, code="SC-01", name="HVAC Services")
        self.assertEqual(SourcingSubcontractor.objects.for_company(self.one).count(), 1)
        self.assertEqual(SourcingSubcontractor.objects.for_company(self.two).count(), 1)

    def test_service_alias_conflicts_are_company_scoped(self):
        SourcingService.objects.create(company=self.one, code="S-01", name="Air Conditioning", aliases=["HVAC"])
        with self.assertRaises(ValidationError):
            SourcingService.objects.create(company=self.one, code="S-02", name="HVAC")
        SourcingService.objects.create(company=self.two, code="S-01", name="HVAC")

    def test_cross_company_contact_and_catalog_are_rejected(self):
        subco = SourcingSubcontractor.objects.create(company=self.one, code="SC-01", name="Mechanical")
        service = SourcingService.objects.create(company=self.two, code="S-01", name="Calibration")
        with self.assertRaises(ValidationError):
            SourcingSubcontractorContact.objects.create(company=self.two, subcontractor=subco, first_name="Cross Tenant")
        with self.assertRaises(ValidationError):
            SourcingSubcontractorService.objects.create(company=self.one, subcontractor=subco, service=service)

    def test_service_rate_and_catalog_verification_are_reference_only(self):
        subco = SourcingSubcontractor.objects.create(company=self.one, code="SC-03", name="Industrial Services")
        service = SourcingService.objects.create(company=self.one, code="SRV-03", name="NDT Inspection")
        with self.assertRaises(ValidationError):
            SourcingSubcontractorService.objects.create(company=self.one, subcontractor=subco, service=service, rate=-1)
        offer = SourcingSubcontractorService.objects.create(company=self.one, subcontractor=subco, service=service)
        self.assertIsNone(offer.rate)
        self.assertEqual(offer.availability, "unknown")
        revision = SourcingSubcontractorServiceRevision.objects.create(
            company=self.one, offer=offer, verified_at=timezone.now(), before={}, after={"availability": "unknown"}
        )
        self.assertEqual(revision.subcontractor_id_snapshot, subco.pk)
        with self.assertRaises(ValidationError):
            revision.save()
        with self.assertRaises(ValidationError):
            revision.delete()
        with self.assertRaises(NotSupportedError):
            SourcingSubcontractorServiceRevision.objects.filter(pk=revision.pk).update(note="edited")

