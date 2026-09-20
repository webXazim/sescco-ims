from __future__ import annotations

from copy import deepcopy
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.schema import validate_supplier_timesheet_pack_snapshot
from apps.documents.services.supplier_timesheet_pack import build_supplier_timesheet_pack_snapshot
from apps.rental_manpower.models import (
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
)
from apps.rental_manpower.services.assignments import assign_worker
from apps.rental_manpower.services.masters import create_project, create_supplier, create_worker


class SupplierTimesheetPackSupplierSummaryContractTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(
            name="Supplier Summary Co",
            legal_name="Supplier Summary Co LLC",
            slug="supplier-summary-co",
        )
        self.user = User.objects.create_user(username="supplier-summary-owner")
        self.owner = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.OWNER,
        )
        self.supplier = create_supplier(
            actor_membership=self.owner,
            code="SUP-SUMMARY",
            name="Supplier Summary Manpower",
        )
        self.project = create_project(
            actor_membership=self.owner,
            code="PRJ-SUMMARY",
            name="Supplier Summary Project",
            start_date=date(2026, 6, 1),
        )
        self.period = RentalTimesheetPeriod.objects.create(
            company=self.company,
            project=self.project,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=RentalTimesheetStatus.LOCKED,
            revision=13,
            locked_at=timezone.now(),
            locked_by=self.user,
        )
        self.worker_one, self.assignment_one = self._worker(
            number="RW-SUM-001",
            name="Summary Worker One",
            trade="Mason",
        )
        self.worker_two, self.assignment_two = self._worker(
            number="RW-SUM-002",
            name="Summary Worker Two",
            trade="Helper",
        )
        self._month(
            worker=self.worker_one,
            assignment=self.assignment_one,
            trade="Mason",
            status_days={27: "A", 28: "L", 29: "OFF", 30: "N"},
            overtime="12",
        )
        self._month(
            worker=self.worker_two,
            assignment=self.assignment_two,
            trade="Helper",
            status_days={},
            overtime="4",
        )

    def _worker(self, *, number: str, name: str, trade: str):
        worker = create_worker(
            actor_membership=self.owner,
            supplier_id=self.supplier.pk,
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

    def _month(self, *, worker, assignment, trade: str, status_days: dict[int, str], overtime: str):
        rows = []
        for day in range(1, 31):
            code = status_days.get(day, "")
            rows.append(
                RentalTimesheetEntry(
                    company=self.company,
                    period=self.period,
                    worker=worker,
                    assignment=assignment,
                    work_date=date(2026, 6, day),
                    regular_hours=Decimal("8") if not code else Decimal("0"),
                    code=code,
                    note="",
                    supplier_code=self.supplier.code,
                    supplier_name=self.supplier.name,
                    project_code=self.project.code,
                    project_name=self.project.name,
                    trade=trade,
                    rate_type="hourly",
                    rate=Decimal("15.00"),
                )
            )
        RentalTimesheetEntry.objects.bulk_create(rows)
        RentalTimesheetOvertime.objects.create(
            company=self.company,
            period=self.period,
            worker=worker,
            assignment=assignment,
            hours=Decimal(overtime),
            rate=Decimal("20.00"),
            supplier_code=self.supplier.code,
            supplier_name=self.supplier.name,
            project_code=self.project.code,
            project_name=self.project.name,
            trade=trade,
            rate_type="hourly",
        )

    def _snapshot(self):
        return build_supplier_timesheet_pack_snapshot(
            self.period,
            supplier_code=self.supplier.code,
        )[0]

    def test_supplier_summary_has_one_reconciled_row_per_worker(self):
        snapshot = self._snapshot()
        validate_supplier_timesheet_pack_snapshot(snapshot)

        rows = snapshot["supplier_summary_rows"]
        self.assertEqual([row["worker_number"] for row in rows], ["RW-SUM-001", "RW-SUM-002"])
        self.assertEqual(rows[0]["trade_display"], "Mason")
        self.assertEqual(rows[0]["work_days"], 26)
        self.assertEqual(rows[0]["absent_days"], 1)
        self.assertEqual(rows[0]["leave_days"], 1)
        self.assertEqual(rows[0]["off_days"], 1)
        self.assertEqual(rows[0]["no_scope_days"], 1)
        self.assertEqual(rows[0]["regular_hours"], "208.00")
        self.assertEqual(rows[0]["overtime_hours"], "12.00")
        self.assertEqual(rows[0]["total_hours"], "220.00")
        self.assertEqual(rows[1]["regular_hours"], "240.00")
        self.assertEqual(rows[1]["overtime_hours"], "4.00")
        self.assertEqual(rows[1]["total_hours"], "244.00")
        self.assertEqual(snapshot["summary"]["regular_hours"], "448.00")
        self.assertEqual(snapshot["summary"]["overtime_hours"], "16.00")
        self.assertEqual(snapshot["summary"]["total_hours"], "464.00")

    def test_supplier_summary_contract_freezes_identity_columns_and_acknowledgement_roles(self):
        snapshot = self._snapshot()
        contract = snapshot["supplier_summary_contract"]

        self.assertEqual(contract["version"], "1.0")
        self.assertEqual(contract["title"], "Supplier Monthly Timesheet Summary")
        self.assertEqual(contract["scope"], "supplier_project_period_locked_revision")
        self.assertEqual(contract["row_basis"], "one_worker_month")
        self.assertEqual(contract["overtime_basis"], "monthly_worker_total")
        self.assertFalse(contract["commercial_values_allowed"])
        self.assertEqual(contract["identity_fields"], ["supplier", "project", "period", "locked_revision"])
        self.assertEqual(
            contract["signature_roles"],
            [
                {"key": "prepared_by", "label": "Prepared by"},
                {"key": "project_approval", "label": "Project / Site Approval"},
                {"key": "supplier_acknowledgement", "label": "Supplier Representative / Acknowledgement"},
            ],
        )
        self.assertEqual(snapshot["supplier"]["code"], "SUP-SUMMARY")
        self.assertEqual(snapshot["project"]["code"], "PRJ-SUMMARY")
        self.assertEqual(snapshot["period_start"], "2026-06-01")
        self.assertEqual(snapshot["period_end"], "2026-06-30")
        self.assertEqual(snapshot["source"]["status"], "locked")
        self.assertEqual(snapshot["source"]["revision"], 13)
        self.assertEqual(snapshot["revision"], 13)

    def test_schema_rejects_tampered_supplier_summary_identity_or_hours(self):
        snapshot = self._snapshot()

        bad_identity = deepcopy(snapshot)
        bad_identity["supplier_summary_rows"][0]["worker_number"] = "RW-TAMPER"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(bad_identity)

        bad_hours = deepcopy(snapshot)
        bad_hours["supplier_summary_rows"][0]["regular_hours"] = "999.00"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(bad_hours)

        bad_status = deepcopy(snapshot)
        bad_status["supplier_summary_rows"][0]["absent_days"] = 2
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(bad_status)

    def test_supplier_summary_rejects_commercial_fields_and_daily_ot(self):
        snapshot = self._snapshot()

        commercial = deepcopy(snapshot)
        commercial["supplier_summary_rows"][0]["rate"] = "15.00"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(commercial)

        daily_ot = deepcopy(snapshot)
        daily_ot["workers"][0]["days"][0]["overtime_hours"] = "1.00"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(daily_ot)

    def test_upgrade4_internal_snapshot_without_supplier_summary_contract_remains_valid(self):
        snapshot = self._snapshot()
        snapshot.pop("supplier_summary_contract")
        snapshot.pop("supplier_summary_rows")
        validate_supplier_timesheet_pack_snapshot(snapshot)
