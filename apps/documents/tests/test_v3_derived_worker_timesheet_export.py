from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import AuditArea, AuditEvent, Company
from apps.documents.delivery import make_delivery_share_token
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.printing import (
    SupplierTimesheetPackWorkerNotFound,
    build_supplier_timesheet_pack_worker_print_context,
)
from apps.documents.tests.test_v3_production_print_renderer import _snapshot


def _hash(value) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SupplierTimesheetPackDerivedWorkerContextTests(SimpleTestCase):
    def test_worker_extract_selects_one_worker_from_immutable_pack_without_mutation(self):
        snapshot = _snapshot(worker_count=3)
        frozen = deepcopy(snapshot)
        target = snapshot["workers"][1]

        context = build_supplier_timesheet_pack_worker_print_context(snapshot, worker_id=target["worker_id"])

        self.assertTrue(context["derived_from_pack"])
        self.assertEqual(context["worker"]["worker_id"], target["worker_id"])
        self.assertEqual(context["worker"]["worker_number"], "RW-PRINT-002")
        self.assertEqual(len(context["worker"]["days"]), 30)
        self.assertEqual(context["worker"]["summary"]["overtime_hours"], "5.00")
        self.assertEqual(snapshot, frozen)
        self.assertNotIn("workers", context)

    def test_worker_extract_rejects_unknown_worker_and_tampered_snapshot(self):
        snapshot = _snapshot(worker_count=2)
        with self.assertRaises(SupplierTimesheetPackWorkerNotFound):
            build_supplier_timesheet_pack_worker_print_context(snapshot, worker_id=uuid.uuid4())

        tampered = deepcopy(snapshot)
        tampered["workers"][0]["days"][0]["overtime_hours"] = "2.00"
        with self.assertRaises(ValidationError):
            build_supplier_timesheet_pack_worker_print_context(
                tampered,
                worker_id=tampered["workers"][0]["worker_id"],
            )


class SupplierTimesheetPackDerivedWorkerRouteTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Derived Worker Export Company",
            legal_name="SESCCO",
            slug="derived-worker-export-company",
        )
        self.user = User.objects.create_user(username="derived-worker-owner", password="strong-password")
        CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.snapshot = _snapshot(worker_count=2)
        self.document = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            document_number="STP-0000101",
            title="Supplier Monthly Timesheet Pack · SUP-PRINT · PRJ-PRINT · June 2026",
            entity_reference="SUP-PRINT",
            entity_name="Print Supplier",
            source_model="rental_manpower.rentaltimesheetperiod:supplier:SUP-PRINT",
            source_id=uuid.uuid4(),
            source_reference="PRJ-PRINT · 2026-06 · R9",
            external_reference="SUP-PRINT:PRJ-PRINT:2026-06:R9",
            snapshot=self.snapshot,
            source_fingerprint="a" * 64,
            snapshot_fingerprint=_hash(self.snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )
        self.client.force_login(self.user)

    def test_internal_worker_print_route_renders_only_selected_worker_without_creating_document(self):
        target = self.snapshot["workers"][1]
        before = BusinessDocument.objects.count()
        response = self.client.get(
            reverse(
                "documents:print-supplier-timesheet-worker",
                kwargs={"document_id": self.document.id, "worker_id": target["worker_id"]},
            )
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("RW-PRINT-002", html)
        self.assertNotIn("RW-PRINT-001", html)
        self.assertIn("Derived from finalized supplier pack", html)
        self.assertIn("Print / Save PDF", html)
        self.assertIn("Full pack", html)
        self.assertEqual(BusinessDocument.objects.count(), before)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow, noarchive")

    def test_internal_worker_print_route_fails_closed_for_unknown_worker_and_non_pack_document(self):
        response = self.client.get(
            reverse(
                "documents:print-supplier-timesheet-worker",
                kwargs={"document_id": self.document.id, "worker_id": uuid.uuid4()},
            )
        )
        self.assertEqual(response.status_code, 404)

        legacy_snapshot = {"kind": DocumentType.RENTAL_TIMESHEET, "project": {"code": "P", "name": "Project"}, "entries": []}
        legacy = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.RENTAL_TIMESHEET,
            document_number="RTS-0000101",
            title="Project Timesheet",
            entity_reference="P",
            entity_name="Project",
            source_model="rental_manpower.rentaltimesheetperiod",
            source_id=uuid.uuid4(),
            snapshot=legacy_snapshot,
            source_fingerprint="b" * 64,
            snapshot_fingerprint=_hash(legacy_snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )
        response = self.client.get(
            reverse(
                "documents:print-supplier-timesheet-worker",
                kwargs={"document_id": legacy.id, "worker_id": self.snapshot["workers"][0]["worker_id"]},
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_supplier_share_worker_print_requires_pack_membership_and_uses_same_immutable_snapshot(self):
        pack = AuditEvent.objects.create(
            company=self.company,
            area=AuditArea.DOCUMENTS,
            action="documents.delivery_pack_issued",
            object_type="documents.DocumentDeliveryPack",
            object_id=str(uuid.uuid4()),
            object_label="DIP-0000301",
            metadata={
                "supplier_code": "SUP-PRINT",
                "supplier_name": "Print Supplier",
                "recipient_name": "Supplier Contact",
                "recipient_email": "supplier@example.com",
                "recipient_phone": "",
                "channel": "email",
                "reference": "JUN-2026",
                "document_ids": [str(self.document.id)],
                "document_numbers": [self.document.document_number],
                "issued_at": timezone.now().isoformat(),
            },
        )
        token = make_delivery_share_token(pack)
        worker = self.snapshot["workers"][0]
        before = BusinessDocument.objects.count()
        response = self.client.get(
            reverse(
                "documents:delivery-pack-shared-worker-print",
                kwargs={
                    "pack_event_id": pack.id,
                    "token": token,
                    "document_id": self.document.id,
                    "worker_id": worker["worker_id"],
                },
            )
        )

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("RW-PRINT-001", html)
        self.assertNotIn("RW-PRINT-002", html)
        self.assertEqual(BusinessDocument.objects.count(), before)
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

        outside_snapshot = _snapshot(worker_count=1)
        outside = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            document_number="STP-0000102",
            title="Outside Pack",
            entity_reference="SUP-PRINT",
            entity_name="Print Supplier",
            source_model="rental_manpower.rentaltimesheetperiod:supplier:SUP-PRINT:outside",
            source_id=uuid.uuid4(),
            source_reference="OUTSIDE",
            external_reference="OUTSIDE-PACK",
            snapshot=outside_snapshot,
            source_fingerprint="c" * 64,
            snapshot_fingerprint=_hash(outside_snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )
        response = self.client.get(
            reverse(
                "documents:delivery-pack-shared-worker-print",
                kwargs={
                    "pack_event_id": pack.id,
                    "token": token,
                    "document_id": outside.id,
                    "worker_id": outside_snapshot["workers"][0]["worker_id"],
                },
            )
        )
        self.assertEqual(response.status_code, 403)
