from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy

from django.core.serializers.json import DjangoJSONEncoder
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.documents.api import _dispatch_delivery_pack_email
from apps.documents.delivery import (
    SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE,
    SUPPLIER_DELIVERY_CONTRACT_VERSION,
    make_delivery_share_token,
    prefer_v3_supplier_timesheets,
    supplier_delivery_document_role,
    supplier_delivery_filename,
)
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.tests.test_v3_production_print_renderer import _snapshot
from apps.rental_manpower.models import ManpowerSupplier


def _hash(value) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SupplierTimesheetPackDeliveryCutoverTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Delivery Cutover Company", legal_name="SESCCO", slug="delivery-cutover-company")
        self.user = User.objects.create_user(username="delivery-cutover-owner", password="strong-password", email="owner@example.com")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.supplier = ManpowerSupplier.objects.create(
            company=self.company,
            code="SUP-PRINT",
            name="Print Supplier",
            contact_person="Supplier Accounts",
            email="supplier@example.com",
            phone="+966500000000",
        )
        self.source_id = uuid.uuid4()
        snapshot = deepcopy(_snapshot(worker_count=2))
        snapshot["source"]["id"] = str(self.source_id)
        self.pack_document = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            document_number="STP-0000201",
            title="Supplier Monthly Timesheet Pack · SUP-PRINT · PRJ-PRINT · June 2026",
            entity_reference="SUP-PRINT",
            entity_name="Print Supplier",
            source_model="rental_manpower.rentaltimesheetperiod:supplier:SUP-PRINT",
            source_id=self.source_id,
            source_reference="PRJ-PRINT · 2026-06 · R9",
            external_reference="SUP-PRINT:PRJ-PRINT:2026-06:R9",
            snapshot=snapshot,
            source_fingerprint="a" * 64,
            snapshot_fingerprint=_hash(snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )
        legacy_snapshot = {
            "kind": DocumentType.RENTAL_TIMESHEET,
            "document_variant": "supplier_timesheet",
            "supplier": {"code": "SUP-PRINT", "name": "Print Supplier"},
            "project": {"code": "PRJ-PRINT", "name": "Print Project"},
            "period_start": "2026-06-01",
            "period_end": "2026-06-30",
            "entries": [],
        }
        self.legacy_document = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.RENTAL_TIMESHEET,
            document_number="RTS-0000201",
            title="Supplier Timesheet Statement · SUP-PRINT",
            entity_reference="SUP-PRINT",
            entity_name="Print Supplier",
            source_model="rental_manpower.rentaltimesheetperiod",
            source_id=self.source_id,
            source_reference="PRJ-PRINT · 2026-06 · R9",
            snapshot=legacy_snapshot,
            source_fingerprint="b" * 64,
            snapshot_fingerprint=_hash(legacy_snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )
        self.client.force_login(self.user)

    def test_delivery_policy_treats_v3_pack_as_primary_and_hides_exact_legacy_replacement(self):
        preferred = prefer_v3_supplier_timesheets([self.legacy_document, self.pack_document])
        self.assertEqual([row.id for row in preferred], [self.pack_document.id])
        self.assertEqual(supplier_delivery_document_role(self.pack_document), "supplier_timesheet_pack")
        self.assertIn("Supplier-Timesheet-Pack", supplier_delivery_filename(self.pack_document))
        self.assertTrue(supplier_delivery_filename(self.pack_document).endswith(".pdf"))

    def test_delivery_options_promotes_v3_pack_and_uses_supplier_master_defaults(self):
        response = self.client.get(reverse("documents:document-delivery-options-api", kwargs={"document_id": self.pack_document.id}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deliveryContractVersion"], SUPPLIER_DELIVERY_CONTRACT_VERSION)
        self.assertEqual(payload["recipientSource"], "supplier_master")
        self.assertEqual(payload["recipient"]["name"], "Supplier Accounts")
        self.assertEqual(payload["recipient"]["email"], "supplier@example.com")
        self.assertEqual(payload["defaultChannel"], "email")
        self.assertEqual([row["id"] for row in payload["documents"]], [str(self.pack_document.id)])
        self.assertTrue(payload["documents"][0]["isPrimaryDelivery"])
        self.assertTrue(payload["documents"][0]["recommended"])
        self.assertEqual(payload["recommendedDocumentIds"], [str(self.pack_document.id)])

    def test_delivery_center_includes_v3_pack_and_suppresses_legacy_equivalent(self):
        response = self.client.get(reverse("documents:document-delivery-center-api"), {"period": "2026-06"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["deliveryContractVersion"], SUPPLIER_DELIVERY_CONTRACT_VERSION)
        self.assertEqual(payload["meta"]["recommended"], 1)
        self.assertEqual(len(payload["groups"]), 1)
        rows = payload["groups"][0]["documents"]
        self.assertEqual([row["id"] for row in rows], [str(self.pack_document.id)])
        self.assertEqual(rows[0]["deliveryRole"], "supplier_timesheet_pack")

    def _issue_pack(self) -> AuditEvent:
        response = self.client.post(
            reverse("documents:document-delivery-pack-api"),
            data=json.dumps({
                "document_ids": [str(self.pack_document.id)],
                "recipient_name": "Supplier Accounts",
                "recipient_email": "supplier@example.com",
                "recipient_phone": "+966500000000",
                "channel": "email",
                "reference": "JUN-2026",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        pack_id = response.json()["pack"]["id"]
        return AuditEvent.objects.get(pk=pack_id)

    def test_issued_pack_freezes_manifest_primary_identity_and_receipt_scope(self):
        pack = self._issue_pack()
        metadata = pack.metadata
        self.assertEqual(metadata["delivery_contract_version"], SUPPLIER_DELIVERY_CONTRACT_VERSION)
        self.assertEqual(metadata["acknowledgement_scope"], SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE)
        self.assertEqual(metadata["primary_document_ids"], [str(self.pack_document.id)])
        self.assertEqual(metadata["primary_timesheet_numbers"], [self.pack_document.document_number])
        self.assertEqual(metadata["document_manifest"][0]["role"], "supplier_timesheet_pack")
        self.assertTrue(metadata["document_manifest"][0]["primary"])
        self.assertIn("Supplier-Timesheet-Pack", metadata["document_manifest"][0]["file_name"])

    def test_supplier_share_renders_primary_full_pack_filename_and_receipt_only_language(self):
        pack = self._issue_pack()
        token = make_delivery_share_token(pack)
        response = self.client.get(reverse("documents:delivery-pack-share", kwargs={"pack_event_id": pack.id, "token": token}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("Primary timesheet", html)
        self.assertIn("Open Full Pack", html)
        self.assertIn("Supplier-Timesheet-Pack", html)
        self.assertIn("Acknowledgement confirms that this supplier document pack was received and opened", html)
        self.assertIn("does not approve, alter, or replace", html)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_supplier_acknowledgement_is_receipt_only_and_retry_safe(self):
        pack = self._issue_pack()
        token = make_delivery_share_token(pack)
        url = reverse("documents:delivery-pack-share-acknowledge", kwargs={"pack_event_id": pack.id, "token": token})
        first = self.client.post(url)
        second = self.client.post(url)
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
        delivered = AuditEvent.objects.filter(
            company=self.company,
            area=AuditArea.DOCUMENTS,
            action="documents.delivery_pack_delivered",
            object_type="documents.DocumentDeliveryPack",
            object_id=pack.object_id,
        )
        self.assertEqual(delivered.count(), 1)
        self.assertEqual(delivered.get().metadata["acknowledgement_scope"], SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE)
        document_event = AuditEvent.objects.filter(
            company=self.company,
            area=AuditArea.DOCUMENTS,
            action="documents.delivery_delivered",
            object_type="documents.BusinessDocument",
            object_id=str(self.pack_document.id),
        ).get()
        self.assertEqual(document_event.metadata["acknowledgement_scope"], SUPPLIER_DELIVERY_ACKNOWLEDGEMENT_SCOPE)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", DEFAULT_FROM_EMAIL="documents@example.com")
    def test_email_dispatch_names_primary_timesheet_and_explains_receipt_only_acknowledgement(self):
        from django.core import mail

        pack = self._issue_pack()
        request = RequestFactory().post("/api/documents/delivery-packs/dispatch/")
        request.company = self.company
        request.company_membership = self.membership
        result, _share_url = _dispatch_delivery_pack_email(request=request, pack_event=pack)
        self.assertEqual(result, "sent")
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertIn("SESCCO Supplier Timesheet", message.subject)
        self.assertIn("Supplier-Timesheet-Pack", message.body)
        self.assertIn("Acknowledgement confirms receipt only", message.body)
