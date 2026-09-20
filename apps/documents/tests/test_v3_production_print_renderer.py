from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.test import SimpleTestCase

from apps.documents.printing import (
    SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE,
    build_supplier_timesheet_pack_print_context,
)
from apps.documents.schema import (
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES,
    SUPPLIER_TIMESHEET_WORKER_SHEET_SIGNATURE_ROLES,
)


def _roles(source):
    return [{"key": key, "label": label} for key, label in source]


def _worker(index: int) -> dict:
    start = date(2026, 6, 1)
    days = []
    for offset in range(30):
        current = start + timedelta(days=offset)
        days.append(
            {
                "date": current.isoformat(),
                "day": current.strftime("%A"),
                "assignment_scope": "assigned",
                "attendance": "Work",
                "attendance_code": "WORK",
                "regular_hours": "8.00",
                "trade": "Mason",
                "note": "",
            }
        )
    number = f"RW-PRINT-{index:03d}"
    return {
        "worker_id": f"00000000-0000-0000-0000-{index:012d}",
        "worker_number": number,
        "worker_name": f"Print Worker {index:03d}",
        "trades": ["Mason"],
        "assignment_segments": [
            {"start": "2026-06-01", "end": "2026-06-30", "trade": "Mason", "recorded_days": 30}
        ],
        "summary": {
            "calendar_days": 30,
            "assigned_days": 30,
            "recorded_days": 30,
            "not_assigned_days": 0,
            "work_days": 30,
            "absent_days": 0,
            "leave_days": 0,
            "off_days": 0,
            "no_scope_days": 0,
            "remark_days": 0,
            "regular_hours": "240.00",
            "overtime_hours": "5.00",
            "total_hours": "245.00",
        },
        "days": days,
    }


def _snapshot(worker_count: int = 1) -> dict:
    workers = [_worker(index) for index in range(1, worker_count + 1)]
    summary_rows = []
    for worker in workers:
        summary = worker["summary"]
        summary_rows.append(
            {
                "worker_id": worker["worker_id"],
                "worker_number": worker["worker_number"],
                "worker_name": worker["worker_name"],
                "trades": ["Mason"],
                "trade_display": "Mason",
                "work_days": summary["work_days"],
                "absent_days": summary["absent_days"],
                "leave_days": summary["leave_days"],
                "off_days": summary["off_days"],
                "no_scope_days": summary["no_scope_days"],
                "regular_hours": summary["regular_hours"],
                "overtime_hours": summary["overtime_hours"],
                "total_hours": summary["total_hours"],
            }
        )

    return {
        "kind": "supplier_timesheet_pack",
        "document_schema_version": "3.0",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "revision": 9,
        "worker_sheet_contract": {
            "version": "1.0",
            "calendar_basis": "full_period",
            "outside_assignment_code": "NOT_ASSIGNED",
            "outside_assignment_label": "Not assigned",
            "overtime_basis": "monthly_worker_total",
            "daily_overtime_allowed": False,
            "signature_roles": _roles(SUPPLIER_TIMESHEET_WORKER_SHEET_SIGNATURE_ROLES),
        },
        "supplier_summary_contract": {
            "version": "1.0",
            "title": "Supplier Monthly Timesheet Summary",
            "scope": "supplier_project_period_locked_revision",
            "row_basis": "one_worker_month",
            "trade_basis": "ordered_distinct_worker_trades",
            "overtime_basis": "monthly_worker_total",
            "commercial_values_allowed": False,
            "columns": [{"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS],
            "identity_fields": list(SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS),
            "signature_roles": _roles(SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES),
        },
        "source": {
            "model": "rental_manpower.rentaltimesheetperiod",
            "id": "10000000-0000-0000-0000-000000000001",
            "status": "locked",
            "revision": 9,
            "locked_at": "2026-07-01T10:00:00+03:00",
        },
        "project": {"code": "PRJ-PRINT", "name": "Print Project"},
        "supplier": {"code": "SUP-PRINT", "name": "Print Supplier"},
        "summary": {
            "worker_count": worker_count,
            "calendar_days": 30 * worker_count,
            "assigned_days": 30 * worker_count,
            "recorded_days": 30 * worker_count,
            "not_assigned_days": 0,
            "work_days": 30 * worker_count,
            "absent_days": 0,
            "leave_days": 0,
            "off_days": 0,
            "no_scope_days": 0,
            "remark_days": 0,
            "regular_hours": f"{240 * worker_count:.2f}",
            "overtime_hours": f"{5 * worker_count:.2f}",
            "total_hours": f"{245 * worker_count:.2f}",
        },
        "supplier_summary_rows": summary_rows,
        "workers": workers,
        "issuer": {"name": "SESCCO", "legal_name": "SESCCO"},
    }


class SupplierTimesheetPackProductionPrintRendererTests(SimpleTestCase):
    def test_renderer_chunks_large_supplier_summary_without_losing_workers(self):
        worker_count = SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE * 2 + 5
        context = build_supplier_timesheet_pack_print_context(_snapshot(worker_count))

        self.assertEqual(context["summary_page_count"], 3)
        self.assertEqual(context["worker_page_count"], worker_count)
        flattened = [row["worker_number"] for page in context["summary_pages"] for row in page["rows"]]
        self.assertEqual(flattened, [f"RW-PRINT-{index:03d}" for index in range(1, worker_count + 1)])
        self.assertFalse(context["summary_pages"][0]["signature_roles"])
        self.assertTrue(context["summary_pages"][-1]["signature_roles"])

    def test_renderer_keeps_complete_worker_calendar_and_monthly_only_overtime(self):
        context = build_supplier_timesheet_pack_print_context(_snapshot())
        worker = context["worker_pages"][0]

        self.assertEqual(worker["period_label"], "June 2026")
        self.assertEqual(len(worker["days"]), 30)
        self.assertEqual(worker["days"][0]["date_label"], "01 Jun 2026")
        self.assertEqual(worker["summary"]["overtime_hours"], "5.00")
        self.assertTrue(all("overtime_hours" not in day for day in worker["days"]))
        self.assertIn("not allocated to individual dates", context["monthly_ot_note"])

    def test_renderer_fails_closed_on_tampered_or_commercial_snapshot(self):
        tampered = deepcopy(_snapshot())
        tampered["workers"][0]["days"][0]["overtime_hours"] = "1.00"
        with self.assertRaises(ValidationError):
            build_supplier_timesheet_pack_print_context(tampered)

        commercial = deepcopy(_snapshot())
        commercial["supplier_summary_rows"][0]["rate"] = "12.00"
        with self.assertRaises(ValidationError):
            build_supplier_timesheet_pack_print_context(commercial)

    def test_template_renders_summary_then_worker_monthly_sheet_without_commercial_columns(self):
        snapshot = _snapshot()
        print_context = build_supplier_timesheet_pack_print_context(snapshot)
        document = SimpleNamespace(
            document_type="supplier_timesheet_pack",
            document_number="STP-0000001",
            period_start=date(2026, 6, 1),
            finalized_at=datetime(2026, 7, 1, 10, 30, tzinfo=timezone.utc),
            source_reference="STP SUP-PRINT PRJ-PRINT 2026-06 R9",
            source_model="rental_manpower.rentaltimesheetperiod:supplier:SUP-PRINT",
        )
        html = render_to_string(
            "documents/print.html",
            {
                "document": document,
                "snapshot": snapshot,
                "headpad_url": "/static/payroll/assets/sescco-company-document-headpad-v2.png",
                "document_label": "Supplier Monthly Timesheet Pack",
                "supplier_timesheet_pack_print": print_context,
            },
        )

        self.assertIn("Supplier Monthly Timesheet Pack", html)
        self.assertIn("Worker Monthly Timesheet", html)
        self.assertIn("RW-PRINT-001", html)
        self.assertIn("01 Jun 2026", html)
        self.assertIn("Monthly OT", html)
        self.assertNotIn(">Rate<", html)
        self.assertNotIn(">Payable<", html)

    def test_worker_page_css_allows_safe_overflow_instead_of_clipping(self):
        template = (Path(settings.BASE_DIR) / "templates" / "documents" / "print.html").read_text(encoding="utf-8")
        self.assertIn(".worker-page { break-inside:auto; page-break-inside:auto; }", template)
        self.assertIn(".worker-table thead { display:table-header-group; }", template)
        self.assertNotIn(".worker-page { height:297mm; overflow:hidden; }", template)
