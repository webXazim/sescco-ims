from __future__ import annotations

from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError

from apps.rental_manpower.models import (
    RentalAttendanceCode,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
)

from ..models import DocumentType
from ..schema import (
    SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS,
    SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES,
    SUPPLIER_TIMESHEET_WORKER_SHEET_CONTRACT_VERSION,
    validate_supplier_timesheet_pack_snapshot,
)


_ZERO = Decimal("0")
_OUTSIDE_ASSIGNMENT_CODE = "NOT_ASSIGNED"
_ATTENDANCE_LABELS = {
    "": "Work",
    RentalAttendanceCode.ABSENT: RentalAttendanceCode.ABSENT.label,
    RentalAttendanceCode.NO_SCOPE: RentalAttendanceCode.NO_SCOPE.label,
    RentalAttendanceCode.LEAVE: RentalAttendanceCode.LEAVE.label,
    RentalAttendanceCode.OFF: RentalAttendanceCode.OFF.label,
}
_SIGNATURE_ROLES = (
    ("prepared_by", "Prepared by"),
    ("project_approval", "Project / Site Approval"),
    ("supplier_acknowledgement", "Supplier Representative / Acknowledgement"),
)
_WORKER_COUNT_KEYS = (
    "calendar_days",
    "assigned_days",
    "recorded_days",
    "not_assigned_days",
    "work_days",
    "absent_days",
    "leave_days",
    "off_days",
    "no_scope_days",
    "remark_days",
)


def _hours(value: Decimal | None) -> str:
    return f"{Decimal(value or 0):.2f}"


def _attendance_label(code: str) -> str:
    return _ATTENDANCE_LABELS.get(str(code or ""), str(code or ""))


def _worker_sheet_contract() -> dict[str, Any]:
    return {
        "version": SUPPLIER_TIMESHEET_WORKER_SHEET_CONTRACT_VERSION,
        "calendar_basis": "full_period",
        "outside_assignment_code": _OUTSIDE_ASSIGNMENT_CODE,
        "outside_assignment_label": "Not assigned",
        "overtime_basis": "monthly_worker_total",
        "daily_overtime_allowed": False,
        "signature_roles": [{"key": key, "label": label} for key, label in _SIGNATURE_ROLES],
    }


def _supplier_summary_contract() -> dict[str, Any]:
    return {
        "version": SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION,
        "title": "Supplier Monthly Timesheet Summary",
        "scope": "supplier_project_period_locked_revision",
        "row_basis": "one_worker_month",
        "trade_basis": "ordered_distinct_worker_trades",
        "overtime_basis": "monthly_worker_total",
        "commercial_values_allowed": False,
        "columns": [
            {"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS
        ],
        "identity_fields": list(SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS),
        "signature_roles": [
            {"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES
        ],
    }


def _supplier_summary_row(worker: dict[str, Any]) -> dict[str, Any]:
    summary = worker["summary"]
    trades = list(worker.get("trades") or [])
    return {
        "worker_id": worker["worker_id"],
        "worker_number": worker["worker_number"],
        "worker_name": worker["worker_name"],
        "trades": trades,
        "trade_display": " / ".join(trades),
        "work_days": int(summary["work_days"]),
        "absent_days": int(summary["absent_days"]),
        "leave_days": int(summary["leave_days"]),
        "off_days": int(summary["off_days"]),
        "no_scope_days": int(summary["no_scope_days"]),
        "regular_hours": summary["regular_hours"],
        "overtime_hours": summary["overtime_hours"],
        "total_hours": summary["total_hours"],
    }


def _new_worker(*, worker_id: object, worker_number: str, worker_name: str) -> dict[str, Any]:
    return {
        "worker_id": str(worker_id),
        "worker_number": str(worker_number or "").strip().upper(),
        "worker_name": str(worker_name or "").strip(),
        "trades": [],
        "assignment_segments": [],
        "summary": {
            "calendar_days": 0,
            "assigned_days": 0,
            "recorded_days": 0,
            "not_assigned_days": 0,
            "work_days": 0,
            "absent_days": 0,
            "leave_days": 0,
            "off_days": 0,
            "no_scope_days": 0,
            "remark_days": 0,
            "regular_hours": "0.00",
            "overtime_hours": "0.00",
            "total_hours": "0.00",
        },
        "days": [],
        "_entry_days": {},
        "_overtime_hours": _ZERO,
    }


def _assignment_segments(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    segments: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_date: date | None = None

    for row in days:
        if row["assignment_scope"] != "assigned":
            previous_date = None
            current = None
            continue
        work_date = date.fromisoformat(row["date"])
        trade = str(row.get("trade") or "").strip()
        contiguous = previous_date is not None and work_date == previous_date + timedelta(days=1)
        if current is None or not contiguous or current["trade"] != trade:
            current = {
                "start": row["date"],
                "end": row["date"],
                "trade": trade,
                "recorded_days": 1,
            }
            segments.append(current)
        else:
            current["end"] = row["date"]
            current["recorded_days"] = int(current["recorded_days"]) + 1
        previous_date = work_date
    return segments


def _materialize_worker_calendar(
    worker: dict[str, Any],
    *,
    period_start: date,
    period_end: date,
) -> dict[str, Any]:
    entry_days: dict[date, dict[str, Any]] = worker.pop("_entry_days")
    overtime_hours: Decimal = worker.pop("_overtime_hours")
    days: list[dict[str, Any]] = []
    counts = {key: 0 for key in _WORKER_COUNT_KEYS}
    regular_hours = _ZERO

    current = period_start
    while current <= period_end:
        counts["calendar_days"] += 1
        source = entry_days.get(current)
        if source is None:
            counts["not_assigned_days"] += 1
            days.append(
                {
                    "date": current.isoformat(),
                    "day": current.strftime("%A"),
                    "assignment_scope": "outside_assignment",
                    "attendance": "Not assigned",
                    "attendance_code": _OUTSIDE_ASSIGNMENT_CODE,
                    "regular_hours": "0.00",
                    "trade": "",
                    "note": "",
                }
            )
            current += timedelta(days=1)
            continue

        counts["assigned_days"] += 1
        counts["recorded_days"] += 1
        code = str(source.get("attendance_code") or "WORK")
        if code == "WORK":
            counts["work_days"] += 1
        elif code == RentalAttendanceCode.ABSENT:
            counts["absent_days"] += 1
        elif code == RentalAttendanceCode.LEAVE:
            counts["leave_days"] += 1
        elif code == RentalAttendanceCode.OFF:
            counts["off_days"] += 1
        elif code == RentalAttendanceCode.NO_SCOPE:
            counts["no_scope_days"] += 1
        if str(source.get("note") or "").strip():
            counts["remark_days"] += 1
        regular_hours += Decimal(source.get("regular_hours") or 0)
        days.append(source)
        current += timedelta(days=1)

    worker["days"] = days
    worker["assignment_segments"] = _assignment_segments(days)
    worker["trades"] = list(OrderedDict((segment["trade"], None) for segment in worker["assignment_segments"]).keys())
    worker["summary"].update(counts)
    worker["summary"]["regular_hours"] = _hours(regular_hours)
    worker["summary"]["overtime_hours"] = _hours(overtime_hours)
    worker["summary"]["total_hours"] = _hours(regular_hours + overtime_hours)
    return worker


def build_supplier_timesheet_pack_snapshot(
    period: RentalTimesheetPeriod,
    *,
    supplier_code: str,
) -> tuple[dict[str, Any], str, str, object, str]:
    """Build the immutable v3 supplier/project/month operational snapshot.

    The locked source is read through two bounded supplier-filtered querysets:
    daily regular attendance rows and monthly overtime rows. The worker sheet is
    then materialized in memory as a complete calendar for the period. Dates on
    which the worker was not assigned to this project are explicitly represented
    as ``outside_assignment`` and never fabricated as attendance.

    Worker, supplier and project commercial rates are never serialized into the
    Supplier Timesheet Pack, and monthly OT is never distributed across dates.
    """

    if period.status != RentalTimesheetStatus.LOCKED:
        raise ValidationError("Supplier Timesheet Packs require a Locked project timesheet.")

    normalized_supplier = str(supplier_code or "").strip().upper()
    if not normalized_supplier:
        raise ValidationError({"supplier_code": "Supplier is required for a Supplier Timesheet Pack."})

    entries = list(
        RentalTimesheetEntry.objects.filter(company_id=period.company_id)
        .filter(period=period, supplier_code__iexact=normalized_supplier)
        .select_related("worker")
        .order_by("worker__worker_number", "work_date", "pk")
    )
    overtime_rows = list(
        RentalTimesheetOvertime.objects.filter(company_id=period.company_id)
        .filter(period=period, supplier_code__iexact=normalized_supplier)
        .select_related("worker")
        .order_by("worker__worker_number", "pk")
    )
    if not entries and not overtime_rows:
        raise ValidationError("The selected supplier has no rows in this locked project timesheet.")

    supplier_name = (
        next((str(row.supplier_name or "").strip() for row in entries if str(row.supplier_name or "").strip()), "")
        or next((str(row.supplier_name or "").strip() for row in overtime_rows if str(row.supplier_name or "").strip()), "")
        or normalized_supplier
    )

    workers: OrderedDict[str, dict[str, Any]] = OrderedDict()

    def ensure_worker(row) -> dict[str, Any]:
        key = str(row.worker_id)
        worker = workers.get(key)
        if worker is None:
            worker = _new_worker(
                worker_id=row.worker_id,
                worker_number=row.worker.worker_number,
                worker_name=row.worker.full_name,
            )
            workers[key] = worker
        return worker

    for row in entries:
        worker = ensure_worker(row)
        regular_hours = Decimal(row.regular_hours or 0)
        code = str(row.code or "")
        worker["_entry_days"][row.work_date] = {
            "date": row.work_date.isoformat(),
            "day": row.work_date.strftime("%A"),
            "assignment_scope": "assigned",
            "attendance": _attendance_label(code),
            "attendance_code": code or "WORK",
            "regular_hours": _hours(regular_hours),
            "trade": str(row.trade or "").strip(),
            "note": str(row.note or "").strip(),
        }

    for row in overtime_rows:
        worker = ensure_worker(row)
        worker["_overtime_hours"] += Decimal(row.hours or 0)

    public_workers: list[dict[str, Any]] = []
    regular_total = _ZERO
    overtime_total = _ZERO
    aggregate_counts = {key: 0 for key in _WORKER_COUNT_KEYS}
    for raw_worker in workers.values():
        worker = _materialize_worker_calendar(
            raw_worker,
            period_start=period.period_start,
            period_end=period.period_end,
        )
        regular_hours = Decimal(worker["summary"]["regular_hours"])
        overtime_hours = Decimal(worker["summary"]["overtime_hours"])
        regular_total += regular_hours
        overtime_total += overtime_hours
        for key in aggregate_counts:
            aggregate_counts[key] += int(worker["summary"].get(key) or 0)
        public_workers.append(worker)

    supplier_summary_rows = [_supplier_summary_row(worker) for worker in public_workers]
    snapshot = {
        "kind": DocumentType.SUPPLIER_TIMESHEET_PACK,
        "document_schema_version": SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION,
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "revision": period.revision,
        "worker_sheet_contract": _worker_sheet_contract(),
        "supplier_summary_contract": _supplier_summary_contract(),
        "source": {
            "model": "rental_manpower.rentaltimesheetperiod",
            "id": str(period.pk),
            "status": period.status,
            "revision": period.revision,
            "locked_at": period.locked_at.isoformat() if period.locked_at else None,
        },
        "project": {
            "code": str(period.project.code or "").strip().upper(),
            "name": str(period.project.name or "").strip(),
        },
        "supplier": {"code": normalized_supplier, "name": supplier_name},
        "summary": {
            "worker_count": len(public_workers),
            **aggregate_counts,
            "regular_hours": _hours(regular_total),
            "overtime_hours": _hours(overtime_total),
            "total_hours": _hours(regular_total + overtime_total),
        },
        "supplier_summary_rows": supplier_summary_rows,
        "workers": public_workers,
    }
    validate_supplier_timesheet_pack_snapshot(snapshot)
    source_reference = f"STP {normalized_supplier} {period.project.code} {period.period_start:%Y-%m} R{period.revision}"
    return snapshot, normalized_supplier, supplier_name, period.period_start, source_reference
