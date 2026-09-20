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


class SupplierTimesheetPackWorkerMonthlySheetContractTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Worker Sheet Co", legal_name="Worker Sheet Co LLC", slug="worker-sheet-co")
        self.user = User.objects.create_user(username="worker-sheet-owner")
        self.owner = CompanyMembership.objects.create(company=self.company, user=self.user, role=AccessRole.OWNER)
        self.supplier = create_supplier(actor_membership=self.owner, code="SUP-SHEET", name="Worker Sheet Supplier")
        self.project = create_project(
            actor_membership=self.owner,
            code="PRJ-SHEET",
            name="Worker Sheet Project",
            start_date=date(2026, 6, 1),
        )
        self.period = RentalTimesheetPeriod.objects.create(
            company=self.company,
            project=self.project,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=RentalTimesheetStatus.LOCKED,
            revision=11,
            locked_at=timezone.now(),
            locked_by=self.user,
        )

    def _worker(self, *, number: str, name: str, trade: str, start_day: int, end_day: int):
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
            effective_date=date(2026, 6, start_day),
        )
        assignment.effective_to = date(2026, 6, end_day)
        assignment.end_reason = "Test period boundary"
        assignment.save(update_fields=["effective_to", "end_reason", "updated_at"])
        return worker, assignment

    def _rows(self, *, worker, assignment, start_day: int, end_day: int, trade: str, note_day: int | None = None):
        RentalTimesheetEntry.objects.bulk_create(
            [
                RentalTimesheetEntry(
                    company=self.company,
                    period=self.period,
                    worker=worker,
                    assignment=assignment,
                    work_date=date(2026, 6, day),
                    regular_hours=Decimal("8"),
                    code="",
                    note="Gate access delay" if day == note_day else "",
                    supplier_code=self.supplier.code,
                    supplier_name=self.supplier.name,
                    project_code=self.project.code,
                    project_name=self.project.name,
                    trade=trade,
                    rate_type="hourly",
                    rate=Decimal("15.00"),
                )
                for day in range(start_day, end_day + 1)
            ]
        )

    def test_partial_assignment_materializes_complete_month_without_fabricating_attendance(self):
        worker, assignment = self._worker(
            number="RW-SHEET-001", name="Partial Worker", trade="Mason", start_day=10, end_day=20
        )
        self._rows(worker=worker, assignment=assignment, start_day=10, end_day=20, trade="Mason", note_day=12)
        RentalTimesheetOvertime.objects.create(
            company=self.company,
            period=self.period,
            worker=worker,
            assignment=assignment,
            hours=Decimal("6"),
            rate=Decimal("20"),
            supplier_code=self.supplier.code,
            supplier_name=self.supplier.name,
            project_code=self.project.code,
            project_name=self.project.name,
            trade="Mason",
            rate_type="hourly",
        )

        snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        validate_supplier_timesheet_pack_snapshot(snapshot)
        sheet = snapshot["workers"][0]

        self.assertEqual(snapshot["worker_sheet_contract"]["version"], "1.0")
        self.assertEqual(snapshot["worker_sheet_contract"]["overtime_basis"], "monthly_worker_total")
        self.assertFalse(snapshot["worker_sheet_contract"]["daily_overtime_allowed"])
        self.assertEqual(len(sheet["days"]), 30)
        self.assertEqual(sheet["summary"]["calendar_days"], 30)
        self.assertEqual(sheet["summary"]["assigned_days"], 11)
        self.assertEqual(sheet["summary"]["recorded_days"], 11)
        self.assertEqual(sheet["summary"]["not_assigned_days"], 19)
        self.assertEqual(sheet["summary"]["remark_days"], 1)
        self.assertEqual(sheet["summary"]["regular_hours"], "88.00")
        self.assertEqual(sheet["summary"]["overtime_hours"], "6.00")
        self.assertEqual(sheet["summary"]["total_hours"], "94.00")
        self.assertEqual(sheet["days"][0]["assignment_scope"], "outside_assignment")
        self.assertEqual(sheet["days"][0]["attendance_code"], "NOT_ASSIGNED")
        self.assertEqual(sheet["days"][9]["assignment_scope"], "assigned")
        self.assertEqual(sheet["days"][9]["trade"], "Mason")
        self.assertEqual(sheet["days"][20]["assignment_scope"], "outside_assignment")
        self.assertNotIn("overtime_hours", sheet["days"][9])
        self.assertEqual(
            sheet["assignment_segments"],
            [{"start": "2026-06-10", "end": "2026-06-20", "trade": "Mason", "recorded_days": 11}],
        )

    def test_trade_change_creates_distinct_non_commercial_assignment_segments(self):
        worker, first = self._worker(
            number="RW-SHEET-002", name="Trade Change Worker", trade="Mason", start_day=1, end_day=14
        )
        second = assign_worker(
            actor_membership=self.owner,
            worker_id=worker.pk,
            project_id=self.project.pk,
            trade="Carpenter",
            rate_type="Hourly",
            rate="18.00",
            effective_date=date(2026, 6, 15),
        )
        second.effective_to = date(2026, 6, 30)
        second.end_reason = "Month end"
        second.save(update_fields=["effective_to", "end_reason", "updated_at"])
        self._rows(worker=worker, assignment=first, start_day=1, end_day=14, trade="Mason")
        self._rows(worker=worker, assignment=second, start_day=15, end_day=30, trade="Carpenter")

        sheet = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]["workers"][0]
        self.assertEqual(sheet["trades"], ["Mason", "Carpenter"])
        self.assertEqual(
            sheet["assignment_segments"],
            [
                {"start": "2026-06-01", "end": "2026-06-14", "trade": "Mason", "recorded_days": 14},
                {"start": "2026-06-15", "end": "2026-06-30", "trade": "Carpenter", "recorded_days": 16},
            ],
        )
        self.assertNotIn("rate", str(sheet).lower())

    def test_worker_sheet_contract_freezes_real_world_acknowledgement_roles(self):
        worker, assignment = self._worker(
            number="RW-SHEET-003", name="Signature Worker", trade="Helper", start_day=1, end_day=30
        )
        self._rows(worker=worker, assignment=assignment, start_day=1, end_day=30, trade="Helper")
        snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        self.assertEqual(
            snapshot["worker_sheet_contract"]["signature_roles"],
            [
                {"key": "prepared_by", "label": "Prepared by"},
                {"key": "project_approval", "label": "Project / Site Approval"},
                {"key": "supplier_acknowledgement", "label": "Supplier Representative / Acknowledgement"},
            ],
        )

    def test_schema_rejects_fabricated_outside_assignment_work_or_trade(self):
        worker, assignment = self._worker(
            number="RW-SHEET-004", name="Boundary Worker", trade="Driver", start_day=10, end_day=20
        )
        self._rows(worker=worker, assignment=assignment, start_day=10, end_day=20, trade="Driver")
        snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]

        bad_hours = deepcopy(snapshot)
        bad_hours["workers"][0]["days"][0]["regular_hours"] = "8.00"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(bad_hours)

        bad_trade = deepcopy(snapshot)
        bad_trade["workers"][0]["days"][0]["trade"] = "Driver"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(bad_trade)

    def test_schema_rejects_missing_calendar_day_and_daily_ot_distribution(self):
        worker, assignment = self._worker(
            number="RW-SHEET-005", name="Calendar Worker", trade="Helper", start_day=1, end_day=30
        )
        self._rows(worker=worker, assignment=assignment, start_day=1, end_day=30, trade="Helper")
        snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]

        missing_day = deepcopy(snapshot)
        missing_day["workers"][0]["days"].pop()
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(missing_day)

        daily_ot = deepcopy(snapshot)
        daily_ot["workers"][0]["days"][0]["overtime_hours"] = "1.00"
        with self.assertRaises(ValidationError):
            validate_supplier_timesheet_pack_snapshot(daily_ot)
