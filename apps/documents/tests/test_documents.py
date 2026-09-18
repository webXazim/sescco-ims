from __future__ import annotations

import hashlib
import json
import uuid
import tempfile
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.core.serializers.json import DjangoJSONEncoder
from django.core.files.base import ContentFile
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db.utils import NotSupportedError
from django.conf import settings
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.services import finalize_business_document, verify_document_snapshot
from apps.documents.services.documents import SESCCO_SUPPLIER_INVOICE_LETTERHEAD, _packaged_brand_asset_snapshot
from apps.documents.delivery import delivery_share_expires_at, make_delivery_share_token, resolve_delivery_share


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


    def test_packaged_sescco_supplier_letterhead_is_a4_hash_verified_and_served(self):
        descriptor = _packaged_brand_asset_snapshot(SESCCO_SUPPLIER_INVOICE_LETTERHEAD)
        asset_path = Path(settings.BASE_DIR) / descriptor["package_path"]
        payload = asset_path.read_bytes()
        self.assertEqual(descriptor["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
        width = int.from_bytes(payload[16:20], "big")
        height = int.from_bytes(payload[20:24], "big")
        self.assertEqual((width, height), (2480, 3508))

        snapshot = dict(self.snapshot)
        snapshot["issuer"] = dict(snapshot["issuer"])
        snapshot["issuer"]["branding"] = {
            "mode": "letterhead", "logo": None, "letterhead": descriptor, "watermark": None,
            "profile": "sescco_supplier_invoice_v1",
        }
        branded = BusinessDocument.objects.create(
            company=self.company, workspace=DocumentWorkspace.RENTAL, document_type=DocumentType.SUPPLIER_INVOICE,
            document_number="SINV-0000001", title="Supplier Invoice · Supplier", entity_reference="SUP-001",
            entity_name="Supplier", source_model="rental_manpower.suppliersettlement", source_id=uuid.uuid4(),
            source_reference="SSET-0001", external_reference="INV-001", snapshot=snapshot,
            source_fingerprint="d" * 64, snapshot_fingerprint=snapshot_hash(snapshot),
            finalized_at=timezone.now(), finalized_by=self.user,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("documents:document-brand-asset", kwargs={"document_id": branded.id, "kind": "letterhead"}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), payload)

    def test_supplier_invoice_finalization_forces_versioned_sescco_headpad(self):
        invoice_snapshot = {
            "kind": DocumentType.SUPPLIER_INVOICE,
            "invoice": {"supplier_invoice_number": "INV-HEADPAD-1", "issue_date": "2026-09-14", "subtotal": "100.00", "vat_amount": "15.00", "vat_rate": "15.00", "total": "115.00", "payment_terms": "30 days"},
            "supplier": {"code": "SUP-001", "name": "Supplier"},
            "project": {"code": "PRJ-001", "name": "Project"},
            "totals": {"net": "100.00"},
            "lines": [],
        }
        fake_source = SimpleNamespace(
            pk=uuid.uuid4(), updated_at=timezone.now(), snapshot_fingerprint="e" * 64, source_fingerprint="",
            _meta=SimpleNamespace(label_lower="rental_manpower.suppliersettlement"),
        )
        payload = (DocumentWorkspace.RENTAL, fake_source, (invoice_snapshot, "SUP-001", "Supplier", timezone.now().date().replace(day=1), "SSET-001"))
        with patch("apps.documents.services.documents._load_source", return_value=payload), patch("apps.documents.services.documents.record_audit_event"):
            document = finalize_business_document(
                actor_membership=self.membership, document_type=DocumentType.SUPPLIER_INVOICE,
                source_id=fake_source.pk, invoice={"invoice_number": "INV-HEADPAD-1"},
            )
        branding = document.snapshot["issuer"]["branding"]
        self.assertEqual(branding["mode"], "letterhead")
        self.assertEqual(branding["profile"], "sescco_supplier_invoice_v1")
        self.assertEqual(branding["letterhead"]["package_path"], SESCCO_SUPPLIER_INVOICE_LETTERHEAD)
        self.assertIsNone(branding["watermark"])
        self.assertEqual(document.snapshot["document_schema_version"], "2.0")
        self.assertTrue(document.snapshot["invoice"]["total_in_words"])

    def test_final_document_cannot_be_saved_updated_or_deleted(self):
        self.document.title = "Changed"
        with self.assertRaises(NotSupportedError):
            self.document.save()
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).update(title="Changed")
        with self.assertRaises(NotSupportedError):
            BusinessDocument.objects.filter(pk=self.document.pk).delete()
    def test_document_directory_is_server_paginated_and_bootstrap_deferred(self):
        from apps.documents.selectors import document_context, document_page_context

        for index in range(1, 76):
            snapshot = {
                "kind": DocumentType.SALARY_SLIP,
                "issuer": {"name": "Document Company"},
                "employee": {"number": f"E-{index:03d}", "name": f"Employee {index:03d}"},
                "net": "100.00",
            }
            BusinessDocument.objects.create(
                company=self.company, workspace=DocumentWorkspace.INTERNAL, document_type=DocumentType.SALARY_SLIP,
                document_number=f"SLIP-{index + 10:07d}", title=f"Salary Slip · Employee {index:03d}",
                entity_reference=f"E-{index:03d}", entity_name=f"Employee {index:03d}",
                source_model="internal_payroll.payrollrunline", source_id=uuid.uuid4(), source_reference="PAYROLL-2026-08",
                snapshot=snapshot, source_fingerprint="c" * 64, snapshot_fingerprint=snapshot_hash(snapshot),
                finalized_at=timezone.now(), finalized_by=self.user,
            )
        bootstrap = document_context(company=self.company, membership=self.membership)
        self.assertTrue(bootstrap["deferred"])
        self.assertEqual(bootstrap["documents"], [])
        page = document_page_context(company=self.company, membership=self.membership, workspace="internal", page=2, page_size=25)
        self.assertEqual(page["surface"], "documents_page")
        self.assertEqual(page["meta"]["pageSize"], 25)
        self.assertEqual(len(page["documents"]), 25)
        self.assertEqual(page["meta"]["count"], 76)
        self.assertEqual(page["summary"]["typeCounts"][DocumentType.SALARY_SLIP], 76)



class SupplierDeliveryShareLifecycleTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Delivery Company", legal_name="Delivery Company LLC", slug="delivery-company")
        self.pack = AuditEvent.objects.create(
            company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack", object_id=str(uuid.uuid4()), object_label="DIP-0000001",
            metadata={"document_ids": [], "recipient_name": "Supplier Contact"},
        )

    @override_settings(DOCUMENT_DELIVERY_SHARE_TTL_SECONDS=3600)
    def test_copying_link_does_not_extend_generation_expiry(self):
        from django.core import signing

        first_token = make_delivery_share_token(self.pack)
        first_payload = signing.loads(first_token, salt="sescco.documents.delivery-pack.v1")
        with patch("apps.documents.delivery.timezone.now", return_value=timezone.now() + timedelta(minutes=30)):
            second_token = make_delivery_share_token(self.pack)
        second_payload = signing.loads(second_token, salt="sescco.documents.delivery-pack.v1")
        self.assertEqual(first_payload["issued_at"], second_payload["issued_at"])
        self.assertEqual(first_payload["issued_at"], int(self.pack.created_at.timestamp()))
        self.assertEqual(
            int(delivery_share_expires_at(self.pack).timestamp()),
            int(self.pack.created_at.timestamp()) + 3600,
        )

    def test_share_revocation_and_rotation_invalidate_old_tokens(self):
        first_token = make_delivery_share_token(self.pack)
        first_share = resolve_delivery_share(pack_event_id=self.pack.id, token=first_token)
        self.assertEqual(first_share.generation, 1)

        AuditEvent.objects.create(
            company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_share_revoked",
            object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id, object_label=self.pack.object_label,
            metadata={"generation": 1},
        )
        with self.assertRaises(PermissionDenied):
            resolve_delivery_share(pack_event_id=self.pack.id, token=first_token)

        AuditEvent.objects.create(
            company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_share_reissued",
            object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id, object_label=self.pack.object_label,
            metadata={"generation": 2},
        )
        second_token = make_delivery_share_token(self.pack)
        second_share = resolve_delivery_share(pack_event_id=self.pack.id, token=second_token)
        self.assertEqual(second_share.generation, 2)
        with self.assertRaises(PermissionDenied):
            resolve_delivery_share(pack_event_id=self.pack.id, token=first_token)


    def test_supplier_open_evidence_is_idempotent(self):
        from apps.documents.views import _record_share_opened

        request = RequestFactory().get("/documents/share/")
        first = _record_share_opened(request=request, pack=self.pack, documents=[])
        second = _record_share_opened(request=request, pack=self.pack, documents=[])

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            AuditEvent.objects.filter(
                company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_opened",
                object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id,
            ).count(),
            1,
        )

    def test_supplier_acknowledgement_records_opened_before_delivered_and_is_retry_safe(self):
        token = make_delivery_share_token(self.pack)
        url = reverse("documents:delivery-pack-share-acknowledge", kwargs={"pack_event_id": self.pack.id, "token": token})

        first = self.client.post(url)
        second = self.client.post(url)

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(
            AuditEvent.objects.filter(
                company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_opened",
                object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id,
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_delivered",
                object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id,
            ).count(),
            1,
        )


class SupplierBulkDispatchTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Bulk Delivery Company", legal_name="Bulk Delivery Company LLC", slug="bulk-delivery-company")
        self.user = User.objects.create_user(username="bulk-delivery-owner", email="owner@example.com")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.pack = AuditEvent.objects.create(
            company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack", object_id=str(uuid.uuid4()), object_label="DIP-0000021",
            metadata={
                "supplier_code": "SUP-001", "supplier_name": "Supplier One",
                "recipient_name": "Supplier Contact", "recipient_email": "supplier@example.com",
                "recipient_phone": "+966500000000", "channel": "email",
                "reference": "JUL-2026", "document_ids": [], "document_numbers": ["STS-0000001"],
                "issued_at": timezone.now().isoformat(),
            },
        )
        self.request = RequestFactory().post("/api/documents/delivery-packs/dispatch/")
        self.request.company = self.company
        self.request.company_membership = self.membership

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="documents@example.com",
    )
    def test_email_dispatch_is_retry_safe_and_records_one_sent_event(self):
        from apps.documents.api import _dispatch_delivery_pack_email

        first, first_url = _dispatch_delivery_pack_email(request=self.request, pack_event=self.pack)
        second, second_url = _dispatch_delivery_pack_email(request=self.request, pack_event=self.pack)

        self.assertEqual(first, "sent")
        self.assertEqual(second, "already_sent")
        self.assertEqual(first_url, second_url)
        self.assertEqual(
            AuditEvent.objects.filter(
                company=self.company, area=AuditArea.DOCUMENTS, action="documents.delivery_pack_dispatched",
                object_type="documents.DocumentDeliveryPack", object_id=self.pack.object_id,
            ).count(),
            1,
        )
