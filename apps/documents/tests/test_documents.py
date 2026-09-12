from __future__ import annotations

import hashlib
import json
import uuid
import tempfile

from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.utils import NotSupportedError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.services import verify_document_snapshot


def snapshot_hash(value) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class BusinessDocumentIntegrityTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Document Company", legal_name="Document Company LLC", slug="document-company")
        self.user = User.objects.create_user(username="document-owner")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
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

    def test_historical_brand_asset_is_hash_verified_and_served(self):
        payload = b"\x89PNG\r\n\x1a\nHISTORICAL-BRAND"
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            storage_key = default_storage.save("company-branding/test/logo.png", ContentFile(payload))
            self.snapshot["issuer"]["branding"] = {
                "mode": "standard",
                "logo": {
                    "storage_key": storage_key,
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "content_type": "image/png",
                },
                "letterhead": None,
                "watermark": None,
            }
            # Create a second immutable document carrying the branding snapshot.
            branded = BusinessDocument.objects.create(
                company=self.company,
                workspace=DocumentWorkspace.INTERNAL,
                document_type=DocumentType.SALARY_SLIP,
                document_number="SLIP-0000002",
                title="Salary Slip · Branded Employee",
                entity_reference="E-002",
                entity_name="Branded Employee",
                source_model="internal_payroll.payrollrunline",
                source_id=uuid.uuid4(),
                source_reference="PAYROLL-2026-08",
                snapshot=self.snapshot,
                source_fingerprint="b" * 64,
                snapshot_fingerprint=snapshot_hash(self.snapshot),
                finalized_at=timezone.now(),
                finalized_by=self.user,
            )
            self.client.force_login(self.user)
            response = self.client.get(reverse("documents:document-brand-asset", kwargs={"document_id": branded.id, "kind": "logo"}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), payload)

    def test_final_document_cannot_be_saved_updated_or_deleted(self):
        self.document.title = "Changed"
        with self.assertRaises(NotSupportedError):
            self.document.save()
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).update(title="Changed")
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).delete()
