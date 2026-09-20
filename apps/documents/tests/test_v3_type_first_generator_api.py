from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType
from apps.documents.services.type_first_generator import type_first_generator_catalog
from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetPeriod, RentalTimesheetStatus
from apps.rental_manpower.services.assignments import assign_worker
from apps.rental_manpower.services.masters import create_project, create_supplier, create_worker


class SupplierTimesheetPackTypeFirstGeneratorApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Generator Co", legal_name="Generator Co LLC", slug="generator-co")
        self.user = User.objects.create_user(username="generator-owner", password="strong-password")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.client.force_login(self.user)
        self.supplier = create_supplier(actor_membership=self.owner, code="SUP-GEN", name="Generator Supplier")
        self.other_supplier = create_supplier(actor_membership=self.owner, code="SUP-OTHER", name="Other Supplier")
        self.project = create_project(actor_membership=self.owner, code="PRJ-GEN", name="Generator Project", start_date=date(2026, 6, 1))
        self.other_project = create_project(actor_membership=self.owner, code="PRJ-OTHER", name="Other Project", start_date=date(2026, 6, 1))
        self.period = self._locked_period(self.project)
        self.other_period = self._locked_period(self.other_project)
        self.worker = self._worker_with_month(self.supplier, self.project, self.period, "RW-GEN-001", "Generator Worker")
        self._worker_with_month(self.other_supplier, self.other_project, self.other_period, "RW-OTHER-001", "Other Worker")

    def _locked_period(self, project):
        return RentalTimesheetPeriod.objects.create(
            company=self.company,
            project=project,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=RentalTimesheetStatus.LOCKED,
            revision=3,
            locked_at=timezone.now(),
            locked_by=self.user,
        )

    def _worker_with_month(self, supplier, project, period, number, name):
        worker = create_worker(actor_membership=self.owner, supplier_id=supplier.pk, worker_number=number, full_name=name)
        assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=project.pk,
            trade="Mason",
            rate_type="Hourly",
            rate="15.00",
            effective_date=date(2026, 6, 1),
        )
        RentalTimesheetEntry.objects.bulk_create([
            RentalTimesheetEntry(
                company=self.company,
                period=period,
                worker=worker,
                assignment=assignment,
                work_date=date(2026, 6, day),
                regular_hours=Decimal("8.00"),
                code="",
                note="",
                supplier_code=supplier.code,
                supplier_name=supplier.name,
                project_code=project.code,
                project_name=project.name,
                trade="Mason",
                rate_type="hourly",
                rate=Decimal("15.00"),
            )
            for day in range(1, 31)
        ])
        return worker

    def test_type_catalog_is_lightweight_and_exposes_only_supplier_facing_single_document_purposes(self):
        with self.assertNumQueries(0):
            static_catalog = type_first_generator_catalog()
        self.assertEqual(len(static_catalog), 4)

        response = self.client.get(reverse("documents:document-generator-types-api"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        keys = [row["key"] for row in payload["types"]]
        self.assertEqual(keys, [
            DocumentType.SUPPLIER_TIMESHEET_PACK,
            DocumentType.SUPPLIER_SETTLEMENT,
            DocumentType.SUPPLIER_INVOICE,
            DocumentType.SUPPLIER_PAYMENT_RECEIPT,
        ])
        self.assertNotIn(DocumentType.RENTAL_TIMESHEET, keys)
        self.assertEqual(payload["selectorMaxPageSize"], 25)
        self.assertIn("generationPlanEndpoint", payload["bulk"])

    def test_supplier_and_project_selectors_are_bounded_and_dependency_scoped(self):
        suppliers = self.client.get(
            reverse("documents:document-generator-suppliers-api"),
            {"type": DocumentType.SUPPLIER_TIMESHEET_PACK, "period": "2026-06", "page_size": "999"},
        )
        self.assertEqual(suppliers.status_code, 200)
        payload = suppliers.json()
        self.assertEqual(payload["meta"]["pageSize"], 25)
        self.assertEqual(payload["meta"]["maxPageSize"], 25)
        self.assertEqual([row["code"] for row in payload["suppliers"]], ["SUP-GEN", "SUP-OTHER"])

        missing_supplier = self.client.get(
            reverse("documents:document-generator-projects-api"),
            {"type": DocumentType.SUPPLIER_TIMESHEET_PACK, "period": "2026-06"},
        )
        self.assertEqual(missing_supplier.status_code, 400)

        projects = self.client.get(
            reverse("documents:document-generator-projects-api"),
            {"type": DocumentType.SUPPLIER_TIMESHEET_PACK, "period": "2026-06", "supplier_code": "SUP-GEN"},
        )
        self.assertEqual(projects.status_code, 200)
        self.assertEqual([row["id"] for row in projects.json()["projects"]], [str(self.project.pk)])

    def test_sources_and_review_resolve_only_the_selected_supplier_project_period(self):
        sources = self.client.get(
            reverse("documents:document-generator-sources-api"),
            {
                "type": DocumentType.SUPPLIER_TIMESHEET_PACK,
                "period": "2026-06",
                "supplier_code": "SUP-GEN",
                "project_id": str(self.project.pk),
            },
        )
        self.assertEqual(sources.status_code, 200)
        source_rows = sources.json()["sources"]
        self.assertEqual(len(source_rows), 1)
        self.assertEqual(source_rows[0]["sourceId"], str(self.period.pk))
        self.assertIsNone(source_rows[0]["existing"])

        review = self.client.post(
            reverse("documents:document-generator-review-api"),
            data=json.dumps({
                "document_type": DocumentType.SUPPLIER_TIMESHEET_PACK,
                "period": "2026-06",
                "supplier_code": "SUP-GEN",
                "project_id": str(self.project.pk),
                "source_id": str(self.period.pk),
            }),
            content_type="application/json",
        )
        self.assertEqual(review.status_code, 200)
        payload = review.json()["review"]
        self.assertEqual(payload["supplier"]["code"], "SUP-GEN")
        self.assertEqual(payload["project"]["id"], str(self.project.pk))
        self.assertEqual(payload["source"]["revision"], 3)
        self.assertEqual(payload["summary"]["workerCount"], 1)
        self.assertEqual(payload["summary"]["regularHours"], "240.00")

        wrong_scope = self.client.post(
            reverse("documents:document-generator-review-api"),
            data=json.dumps({
                "document_type": DocumentType.SUPPLIER_TIMESHEET_PACK,
                "period": "2026-06",
                "supplier_code": "SUP-GEN",
                "project_id": str(self.other_project.pk),
                "source_id": str(self.period.pk),
            }),
            content_type="application/json",
        )
        self.assertEqual(wrong_scope.status_code, 400)

    def test_type_first_create_is_the_only_api_path_that_can_activate_v3_pack(self):
        body = {
            "document_type": DocumentType.SUPPLIER_TIMESHEET_PACK,
            "period": "2026-06",
            "supplier_code": "SUP-GEN",
            "project_id": str(self.project.pk),
            "source_id": str(self.period.pk),
        }
        generic = self.client.post(
            reverse("documents:documents-api"),
            data=json.dumps({
                "document_type": DocumentType.SUPPLIER_TIMESHEET_PACK,
                "source_id": str(self.period.pk),
                "supplier_code": "SUP-GEN",
            }),
            content_type="application/json",
        )
        self.assertEqual(generic.status_code, 400)
        self.assertFalse(BusinessDocument.objects.filter(document_type=DocumentType.SUPPLIER_TIMESHEET_PACK).exists())

        response = self.client.post(
            reverse("documents:document-generator-create-api"),
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        document = response.json()["document"]
        self.assertEqual(document["type"], DocumentType.SUPPLIER_TIMESHEET_PACK)
        self.assertTrue(document["number"].startswith("STP-"))
        self.assertEqual(document["snapshot"]["document_schema_version"], "3.0")
        self.assertEqual(BusinessDocument.objects.filter(document_type=DocumentType.SUPPLIER_TIMESHEET_PACK).count(), 1)

        sources = self.client.get(
            reverse("documents:document-generator-sources-api"),
            {"type": DocumentType.SUPPLIER_TIMESHEET_PACK, "period": "2026-06", "supplier_code": "SUP-GEN", "project_id": str(self.project.pk)},
        )
        self.assertEqual(sources.status_code, 200)
        self.assertEqual(sources.json()["sources"][0]["existing"]["id"], document["id"])

    def test_type_first_routes_do_not_expose_project_timesheet_or_unbounded_all_scope(self):
        unsupported = self.client.get(
            reverse("documents:document-generator-suppliers-api"),
            {"type": DocumentType.RENTAL_TIMESHEET, "period": "2026-06"},
        )
        self.assertEqual(unsupported.status_code, 400)
        self.assertNotIn("allSuppliers", json.dumps(self.client.get(reverse("documents:document-generator-types-api")).json()))
