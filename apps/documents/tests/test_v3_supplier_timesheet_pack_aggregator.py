from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType
from apps.documents.schema import validate_supplier_timesheet_pack_snapshot
from apps.documents.services.documents import _load_source, finalize_business_document
from apps.documents.services.supplier_timesheet_pack import build_supplier_timesheet_pack_snapshot
from apps.rental_manpower.models import (
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
)
from apps.rental_manpower.services.assignments import assign_worker
from apps.rental_manpower.services.masters import create_project, create_supplier, create_worker


class SupplierTimesheetPackAggregatorTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Pack Co", legal_name="Pack Co LLC", slug="pack-co")
        self.user = User.objects.create_user(username="pack-owner")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.client.force_login(self.user)
        self.supplier = create_supplier(actor_membership=self.owner, code="SUP-PACK", name="Pack Supplier")
        self.other_supplier = create_supplier(actor_membership=self.owner, code="SUP-OTHER", name="Other Supplier")
        self.project = create_project(
            actor_membership=self.owner,
            code="PRJ-PACK",
            name="Pack Project",
            start_date=date(2026, 6, 1),
        )
        self.period = RentalTimesheetPeriod.objects.create(
            company=self.company,
            project=self.project,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=RentalTimesheetStatus.LOCKED,
            revision=7,
            locked_at=timezone.now(),
            locked_by=self.user,
        )
        self.worker_one, self.assignment_one = self._add_worker(
            supplier=self.supplier, number="RW-PACK-001", name="Worker One", trade="Mason"
        )
        self.worker_two, self.assignment_two = self._add_worker(
            supplier=self.supplier, number="RW-PACK-002", name="Worker Two", trade="Helper"
        )
        self.other_worker, self.other_assignment = self._add_worker(
            supplier=self.other_supplier, number="RW-OTHER-001", name="Other Worker", trade="Driver"
        )
        self._add_month(
            worker=self.worker_one,
            assignment=self.assignment_one,
            supplier=self.supplier,
            trade="Mason",
            absent_day=29,
            off_day=30,
            overtime="12",
        )
        self._add_month(
            worker=self.worker_two,
            assignment=self.assignment_two,
            supplier=self.supplier,
            trade="Helper",
            overtime="4",
        )
        self._add_month(
            worker=self.other_worker,
            assignment=self.other_assignment,
            supplier=self.other_supplier,
            trade="Driver",
            overtime="20",
        )

    def _add_worker(self, *, supplier, number: str, name: str, trade: str):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=supplier.pk,
            worker_number=number,
            full_name=name,
        )
        assignment = assign_worker(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            trade=trade,
            rate_type="Hourly",
            rate="15.00",
            effective_date=date(2026, 6, 1),
        )
        return worker, assignment

    def _add_month(
        self,
        *,
        worker,
        assignment,
        supplier,
        trade: str,
        absent_day: int | None = None,
        off_day: int | None = None,
        overtime: str = "0",
    ) -> None:
        rows = []
        for day in range(1, 31):
            code = ""
            hours = Decimal("8")
            if day == absent_day:
                code, hours = "A", Decimal("0")
            elif day == off_day:
                code, hours = "OFF", Decimal("0")
            rows.append(
                RentalTimesheetEntry(
                    company=self.company,
                    period=self.period,
                    worker=worker,
                    assignment=assignment,
                    work_date=date(2026, 6, day),
                    regular_hours=hours,
                    code=code,
                    note="",
                    supplier_code=supplier.code,
                    supplier_name=supplier.name,
                    project_code=self.project.code,
                    project_name=self.project.name,
                    trade=trade,
                    rate_type="hourly",
                    rate=Decimal("15.00"),
                )
            )
        RentalTimesheetEntry.objects.bulk_create(rows)
        if Decimal(overtime) > 0:
            RentalTimesheetOvertime.objects.create(
                company=self.company,
                period=self.period,
                worker=worker,
                assignment=assignment,
                hours=Decimal(overtime),
                rate=Decimal("20.00"),
                supplier_code=supplier.code,
                supplier_name=supplier.name,
                project_code=self.project.code,
                project_name=self.project.name,
                trade=trade,
                rate_type="hourly",
            )

    def test_aggregator_builds_supplier_scoped_summary_and_worker_daily_detail(self):
        snapshot, code, name, period_start, source_reference = build_supplier_timesheet_pack_snapshot(
            self.period, supplier_code="sup-pack"
        )
        validate_supplier_timesheet_pack_snapshot(snapshot)
        self.assertEqual(code, "SUP-PACK")
        self.assertEqual(name, "Pack Supplier")
        self.assertEqual(period_start, date(2026, 6, 1))
        self.assertIn("R7", source_reference)
        self.assertEqual(snapshot["document_schema_version"], "3.0")
        self.assertEqual(snapshot["source"]["revision"], 7)
        self.assertEqual(snapshot["summary"]["worker_count"], 2)
        self.assertEqual(snapshot["summary"]["regular_hours"], "464.00")
        self.assertEqual(snapshot["summary"]["overtime_hours"], "16.00")
        self.assertEqual(snapshot["summary"]["total_hours"], "480.00")
        self.assertEqual(snapshot["summary"]["work_days"], 58)
        self.assertEqual(snapshot["summary"]["absent_days"], 1)
        self.assertEqual(snapshot["summary"]["off_days"], 1)
        self.assertEqual([row["worker_number"] for row in snapshot["workers"]], ["RW-PACK-001", "RW-PACK-002"])
        self.assertEqual(len(snapshot["workers"][0]["days"]), 30)
        self.assertEqual(snapshot["workers"][0]["summary"]["regular_hours"], "224.00")
        self.assertEqual(snapshot["workers"][0]["summary"]["overtime_hours"], "12.00")
        self.assertEqual(snapshot["workers"][0]["days"][28]["attendance"], "Absent")
        self.assertEqual(snapshot["workers"][0]["days"][29]["attendance"], "Off")
        self.assertNotIn("overtime_hours", snapshot["workers"][0]["days"][0])
        self.assertNotIn('"rate":', json.dumps(snapshot).lower())
        self.assertNotIn("RW-OTHER-001", json.dumps(snapshot))

    def test_aggregator_is_deterministic(self):
        first = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        second = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        self.assertEqual(first, second)

    def test_aggregator_uses_two_supplier_filtered_data_queries_independent_of_worker_count(self):
        # Period/project are already materialized. The aggregator should read only daily rows and monthly OT.
        with self.assertNumQueries(2):
            snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        self.assertEqual(snapshot["summary"]["worker_count"], 2)

    def test_source_dispatch_is_constant_three_queries_and_does_not_prefetch_whole_project(self):
        with self.assertNumQueries(3):
            workspace, source, payload = _load_source(
                company=self.company,
                document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
                source_id=self.period.pk,
                supplier_code=self.supplier.code,
            )
        self.assertEqual(workspace, "rental")
        self.assertEqual(source.pk, self.period.pk)
        self.assertEqual(payload[0]["summary"]["worker_count"], 2)

    def test_pack_rejects_unlocked_or_empty_supplier_source(self):
        self.period.status = RentalTimesheetStatus.APPROVED
        with self.assertRaises(ValidationError):
            build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)
        self.period.status = RentalTimesheetStatus.LOCKED
        with self.assertRaises(ValidationError):
            build_supplier_timesheet_pack_snapshot(self.period, supplier_code="SUP-MISSING")

    def test_internal_finalizer_creates_one_supplier_qualified_v3_document(self):
        document = finalize_business_document(
            actor_membership=self.owner,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            source_id=self.period.pk,
            supplier_code=self.supplier.code,
            allow_supplier_timesheet_pack=True,
        )
        self.assertEqual(document.document_type, DocumentType.SUPPLIER_TIMESHEET_PACK)
        self.assertTrue(document.document_number.startswith("STP-"))
        self.assertEqual(document.snapshot["document_schema_version"], "3.0")
        self.assertEqual(document.entity_reference, "SUP-PACK")
        self.assertEqual(
            document.source_model,
            "rental_manpower.rentaltimesheetperiod:supplier:SUP-PACK",
        )
        self.assertEqual(BusinessDocument.objects.filter(document_type=DocumentType.SUPPLIER_TIMESHEET_PACK).count(), 1)
        self.assertEqual(len(document.source_fingerprint), 64)
        self.assertEqual(len(document.snapshot_fingerprint), 64)

    def test_generic_documents_api_keeps_v3_creation_closed_until_generator_cutover(self):
        response = self.client.post(
            reverse("documents:documents-api"),
            data=json.dumps(
                {
                    "document_type": DocumentType.SUPPLIER_TIMESHEET_PACK,
                    "source_id": str(self.period.pk),
                    "supplier_code": self.supplier.code,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not yet exposed", response.json()["errors"]["document_type"][0])
        self.assertFalse(BusinessDocument.objects.filter(document_type=DocumentType.SUPPLIER_TIMESHEET_PACK).exists())
