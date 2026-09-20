from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.serializers.json import DjangoJSONEncoder
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType, DocumentWorkspace
from apps.documents.selectors import document_page_context


ROOT = Path(__file__).resolve().parents[3]
JS_PATH = ROOT / "static" / "payroll" / "js" / "app.js"
CSS_PATH = ROOT / "static" / "payroll" / "css" / "v2" / "pages" / "payroll.css"
API_PATH = ROOT / "apps" / "documents" / "api.py"
SELECTOR_PATH = ROOT / "apps" / "documents" / "selectors" / "documents.py"


def _snapshot_hash(value) -> str:
    payload = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _pack_snapshot() -> dict[str, object]:
    return {
        "kind": DocumentType.SUPPLIER_TIMESHEET_PACK,
        "document_schema_version": "3.0",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "revision": 6,
        "source": {
            "model": "rental_manpower.rentaltimesheetperiod",
            "id": "11111111-1111-1111-1111-111111111111",
            "status": "locked",
            "revision": 6,
        },
        "project": {"code": "P-001", "name": "Project 001"},
        "supplier": {"code": "SUP-001", "name": "Supplier 001"},
        "summary": {
            "worker_count": 1,
            "regular_hours": "8.00",
            "overtime_hours": "2.00",
            "total_hours": "10.00",
        },
        "workers": [
            {
                "worker_id": "22222222-2222-2222-2222-222222222222",
                "worker_number": "RW-001",
                "worker_name": "Worker 001",
                "summary": {"regular_hours": "8.00", "overtime_hours": "2.00", "total_hours": "10.00"},
                "days": [
                    {
                        "date": "2026-06-01",
                        "day": "Monday",
                        "attendance": "WORK",
                        "regular_hours": "8.00",
                        "trade": "Mason",
                        "note": "",
                    }
                ],
            }
        ],
    }


class SupplierTimesheetPackV3DocumentsWorkspaceCleanupRuntimeTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Document Workspace Company", slug="document-workspace-company")
        self.user = User.objects.create_user(username="document-workspace-owner")
        self.membership = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        snapshot = _pack_snapshot()
        self.document = BusinessDocument.objects.create(
            company=self.company,
            workspace=DocumentWorkspace.RENTAL,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            document_number="STP-0000001",
            title="Supplier Monthly Timesheet Pack · Supplier 001 · Project 001",
            entity_reference="SUP-001",
            entity_name="Supplier 001",
            source_model="rental_manpower.rentaltimesheetperiod",
            source_id=uuid.uuid4(),
            source_reference="STP SUP-001 P-001 2026-06 R6",
            snapshot=snapshot,
            source_fingerprint="a" * 64,
            snapshot_fingerprint=_snapshot_hash(snapshot),
            finalized_at=timezone.now(),
            finalized_by=self.user,
        )

    def test_register_page_defers_snapshot_integrity_and_uses_supplier_timesheet_family_count(self):
        with patch("apps.documents.selectors.documents.verify_document_snapshot", side_effect=AssertionError("register must not hash full snapshots")):
            page = document_page_context(
                company=self.company,
                membership=self.membership,
                workspace="rental",
                page=1,
                page_size=25,
            )
        self.assertEqual(page["summary"]["typeCounts"]["supplier_timesheet"], 1)
        self.assertNotIn(DocumentType.SUPPLIER_TIMESHEET_PACK, page["summary"]["typeCounts"])
        self.assertIsNone(page["documents"][0]["integrityOk"])
        self.assertEqual(page["documents"][0]["integrityStatus"], "deferred")
        self.assertNotIn("snapshot", page["documents"][0])

    def test_summary_detail_returns_small_preview_without_worker_array(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("documents:document-detail-api", kwargs={"document_id": self.document.id}),
            {"view": "summary"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["document"]
        self.assertEqual(payload["previewMode"], "summary")
        self.assertEqual(payload["preview"]["summary"]["worker_count"], 1)
        self.assertEqual(payload["preview"]["supplier"]["code"], "SUP-001")
        self.assertNotIn("snapshot", payload)
        self.assertNotIn("workers", json.dumps(payload["preview"]))
        self.assertEqual(payload["integrityStatus"], "deferred")

    def test_full_detail_remains_backward_compatible_and_integrity_verified(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("documents:document-detail-api", kwargs={"document_id": self.document.id}))
        self.assertEqual(response.status_code, 200)
        payload = response.json()["document"]
        self.assertEqual(payload["previewMode"], "full")
        self.assertEqual(len(payload["snapshot"]["workers"]), 1)
        self.assertTrue(payload["integrityOk"])


class SupplierTimesheetPackV3DocumentsWorkspaceCleanupStaticTests(SimpleTestCase):
    def setUp(self):
        self.js = JS_PATH.read_text(encoding="utf-8")
        self.css = CSS_PATH.read_text(encoding="utf-8")
        self.api = API_PATH.read_text(encoding="utf-8")
        self.selector = SELECTOR_PATH.read_text(encoding="utf-8")

    def test_rental_workspace_has_four_business_families_and_project_timesheet_stays_secondary(self):
        start = self.js.index("const rentalFamilies=[")
        end = self.js.index("const internalFamilies=[", start)
        families = self.js[start:end]
        for key in ("supplier_timesheet", "supplier_settlement", "supplier_invoice", "supplier_payment_receipt"):
            self.assertIn(key, families)
        self.assertNotIn("rental_timesheet", families)
        self.assertIn("All records", self.js)
        self.assertIn("Open Project Timesheets", self.js)
        self.assertIn("data-document-project-timesheets", self.js)

    def test_documents_toolbar_removes_redundant_final_status_filter(self):
        start = self.js.index("function documentsTemplate()")
        end = self.js.index("function documentSourceTypesForWorkspace", start)
        template = self.js[start:end]
        self.assertNotIn("documentStatusFilter", template)
        self.assertIn("document-toolbar--clean", template)
        self.assertIn("Search document number, supplier, project or source", template)

    def test_browser_requests_summary_preview_instead_of_full_snapshot(self):
        start = self.js.index("async function loadDocumentDetail")
        end = self.js.index("function documentPreviewSummaryValues", start)
        loader = self.js[start:end]
        self.assertIn("?view=summary", loader)
        self.assertIn("full.preview||full.snapshot", self.js)
        self.assertIn("Preview stays lightweight", self.js)

    def test_backend_register_and_summary_paths_explicitly_defer_large_snapshot(self):
        self.assertIn('Paginator(filtered.defer("snapshot"), size)', self.selector)
        self.assertIn("verify_integrity=False", self.selector)
        self.assertIn("def document_preview_fragment", self.selector)
        self.assertNotIn('"snapshot__workers"', self.selector[self.selector.index("def document_preview_fragment"):self.selector.index("def document_page_context")])
        self.assertIn('summary_only = request.GET.get("view", "").strip().lower() == "summary"', self.api)
        self.assertIn('row_qs.defer("snapshot") if summary_only', self.api)

    def test_workspace_cleanup_has_dedicated_responsive_layout(self):
        for hook in (
            "document-workspace-note",
            "document-toolbar--clean",
            "documents-page--clean",
            "document-native-preview__note",
        ):
            self.assertIn(hook, self.css)
