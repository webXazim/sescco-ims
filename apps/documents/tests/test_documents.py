from __future__ import annotations

import hashlib
import json
import uuid

from django.core.serializers.json import DjangoJSONEncoder
from django.db.utils import NotSupportedError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.services import verify_document_snapshot
from apps.documents.services.documents import _amount_in_words


def snapshot_hash(value) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BusinessDocumentIntegrityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Document Company", legal_name="Document Company LLC", slug="document-company")
        self.user = User.objects.create_user(username="document-owner")
        self.snapshot = {
            "kind": DocumentType.SALARY_SLIP,
            "issuer": {"name": "Document Company", "legal_name": "Document Company LLC", "currency": "SAR", "country": "SA", "timezone": "Asia/Riyadh"},
            "employee": {"number": "E-001", "name": "Employee"},
            "net": "100.00",
        }
        self.document = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.INTERNAL,
            document_type=DocumentType.SALARY_SLIP,
            document_number="SLIP-0000001",
            title="Salary Slip · Employee",
            entity_reference="E-001",
            entity_name="Employee",
            source_model="internal_payroll.payrollrunline",
            source_id=uuid.uuid4(),
            source_reference="PAYROLL-2026-08",
            snapshot=self.snapshot,
            source_fingerprint="a" * 64,
            snapshot_fingerprint=snapshot_hash(self.snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )

    def test_final_document_snapshot_verifies(self):
        self.assertTrue(verify_document_snapshot(self.document))

    def test_in_memory_snapshot_tamper_is_detected(self):
        self.document.snapshot["net"] = "999.00"
        self.assertFalse(verify_document_snapshot(self.document))

    def test_final_document_cannot_be_saved_updated_or_deleted(self):
        self.document.title = "Changed"
        with self.assertRaises(NotSupportedError):
            self.document.save()
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).update(title="Changed")
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).delete()


class SalarySlipReferenceOutputTests(TestCase):
    def test_amount_in_words_matches_salary_slip_business_output(self):
        self.assertEqual(_amount_in_words("2415.00", "SAR"), "Two Thousand Four Hundred Fifteen Saudi Riyals Only")
        self.assertEqual(_amount_in_words("100.50", "SAR"), "One Hundred Saudi Riyals and Fifty Halalas Only")
