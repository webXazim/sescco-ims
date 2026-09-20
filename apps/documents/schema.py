from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError


LEGACY_DOCUMENT_SCHEMA_VERSION = "2.0"
SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION = "3.0"
SUPPLIER_TIMESHEET_PACK_TYPE = "supplier_timesheet_pack"
SUPPLIER_TIMESHEET_WORKER_SHEET_CONTRACT_VERSION = "1.0"
SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION = "1.0"

FINANCIAL_RECONCILIATION_CONTRACT_VERSION = "1.0"
FINANCIAL_RECONCILIATION_DOCUMENT_TYPES = frozenset({
    "supplier_settlement",
    "supplier_invoice",
    "supplier_payment_receipt",
})
SUPPLIER_TIMESHEET_WORKER_SHEET_ATTENDANCE = {
    "WORK": "Work",
    "A": "Absent",
    "N": "No Scope",
    "L": "Leave",
    "OFF": "Off",
}
SUPPLIER_TIMESHEET_WORKER_SHEET_SIGNATURE_ROLES = (
    ("prepared_by", "Prepared by"),
    ("project_approval", "Project / Site Approval"),
    ("supplier_acknowledgement", "Supplier Representative / Acknowledgement"),
)
SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS = (
    ("worker_number", "Worker No."),
    ("worker_name", "Worker"),
    ("trade_display", "Trade"),
    ("work_days", "Work Days"),
    ("absent_days", "Absent"),
    ("leave_days", "Leave"),
    ("off_days", "Off"),
    ("no_scope_days", "No Scope"),
    ("regular_hours", "Regular Hrs"),
    ("overtime_hours", "OT Hrs"),
    ("total_hours", "Total Hrs"),
)
SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS = (
    "supplier",
    "project",
    "period",
    "locked_revision",
)
SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES = SUPPLIER_TIMESHEET_WORKER_SHEET_SIGNATURE_ROLES
SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COUNT_KEYS = (
    "work_days",
    "absent_days",
    "leave_days",
    "off_days",
    "no_scope_days",
)
SUPPLIER_TIMESHEET_WORKER_SHEET_COUNT_KEYS = (
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

# Timesheet evidence must remain operational, not commercial. Monetary/rate fields
# belong to Supplier Settlement documents and are rejected recursively from v3 packs.
SUPPLIER_TIMESHEET_PACK_FORBIDDEN_KEYS = frozenset(
    {
        "amount",
        "base",
        "base_amount",
        "gross",
        "gross_amount",
        "net",
        "net_amount",
        "payable",
        "rate",
        "rate_type",
        "regular_rate",
        "overtime_rate",
        "hourly_rate",
        "adjustment_earnings",
        "adjustment_deductions",
        "vat_amount",
        "vat_rate",
        "subtotal",
        "total_payable",
    }
)

# Rental overtime authority is monthly per worker. A v3 worker page may show that
# monthly total, but a daily row must never invent/distribute OT across dates.
SUPPLIER_TIMESHEET_PACK_DAILY_OT_KEYS = frozenset(
    {"overtime", "overtime_hours", "ot", "ot_hours", "daily_overtime", "daily_ot_hours"}
)


def document_schema_version_for_type(document_type: str) -> str:
    return (
        SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION
        if str(document_type or "").strip() == SUPPLIER_TIMESHEET_PACK_TYPE
        else LEGACY_DOCUMENT_SCHEMA_VERSION
    )


def _require_mapping(value: Any, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationError({field: "Must be an object."})
    return value


def _require_text(mapping: Mapping[str, Any], key: str, *, field: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValidationError({field: f"{key} is required."})
    return value


def _require_decimal(mapping: Mapping[str, Any], key: str, *, field: str) -> Decimal:
    if key not in mapping:
        raise ValidationError({field: f"{key} is required."})
    try:
        value = Decimal(str(mapping.get(key)))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: f"{key} must be a decimal value."}) from exc
    if not value.is_finite() or value < 0:
        raise ValidationError({field: f"{key} must be a non-negative finite decimal value."})
    return value


def _require_non_negative_int(mapping: Mapping[str, Any], key: str, *, field: str) -> int:
    if key not in mapping:
        raise ValidationError({field: f"{key} is required."})
    raw = mapping.get(key)
    if isinstance(raw, bool):
        raise ValidationError({field: f"{key} must be a non-negative integer."})
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({field: f"{key} must be a non-negative integer."}) from exc
    if value < 0 or str(value) != str(raw).strip():
        raise ValidationError({field: f"{key} must be a non-negative integer."})
    return value


def _require_iso_date(mapping: Mapping[str, Any], key: str, *, field: str) -> date:
    value = _require_text(mapping, key, field=field)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({field: f"{key} must use ISO YYYY-MM-DD format."}) from exc


def _walk_forbidden_commercial_fields(value: Any, *, path: str = "snapshot") -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key in SUPPLIER_TIMESHEET_PACK_FORBIDDEN_KEYS:
                raise ValidationError({"snapshot": f"Supplier Timesheet Pack cannot contain commercial field '{path}.{key}'."})
            _walk_forbidden_commercial_fields(child, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            _walk_forbidden_commercial_fields(child, path=f"{path}[{index}]")


def _validate_worker_sheet_contract(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw_contract = data.get("worker_sheet_contract")
    if raw_contract is None:
        # Compatibility: internal-only v3 snapshots finalized during Upgrade 3 remain
        # structurally valid. All snapshots created by the Upgrade 4 aggregator carry
        # this contract and therefore receive the stricter real-world page checks below.
        return None
    contract = _require_mapping(raw_contract, field="snapshot")
    if _require_text(contract, "version", field="snapshot") != SUPPLIER_TIMESHEET_WORKER_SHEET_CONTRACT_VERSION:
        raise ValidationError({"snapshot": "worker_sheet_contract.version must be 1.0."})
    if _require_text(contract, "calendar_basis", field="snapshot") != "full_period":
        raise ValidationError({"snapshot": "worker_sheet_contract.calendar_basis must be full_period."})
    if _require_text(contract, "outside_assignment_code", field="snapshot") != "NOT_ASSIGNED":
        raise ValidationError({"snapshot": "worker_sheet_contract.outside_assignment_code must be NOT_ASSIGNED."})
    if _require_text(contract, "outside_assignment_label", field="snapshot") != "Not assigned":
        raise ValidationError({"snapshot": "worker_sheet_contract.outside_assignment_label must be 'Not assigned'."})
    if _require_text(contract, "overtime_basis", field="snapshot") != "monthly_worker_total":
        raise ValidationError({"snapshot": "worker_sheet_contract.overtime_basis must be monthly_worker_total."})
    if contract.get("daily_overtime_allowed") is not False:
        raise ValidationError({"snapshot": "worker_sheet_contract.daily_overtime_allowed must be false."})

    signatures = contract.get("signature_roles")
    if not isinstance(signatures, list):
        raise ValidationError({"snapshot": "worker_sheet_contract.signature_roles must be a list."})
    expected = [{"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_WORKER_SHEET_SIGNATURE_ROLES]
    if signatures != expected:
        raise ValidationError({"snapshot": "worker_sheet_contract.signature_roles must use the frozen worker-sheet acknowledgement roles."})
    return contract


def _validate_supplier_summary_contract(data: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw_contract = data.get("supplier_summary_contract")
    if raw_contract is None:
        # Compatibility: internal-only v3 snapshots finalized through Upgrade 4
        # predate the supplier-summary contract. New Upgrade 5 snapshots always
        # include it and receive the supplier-facing first-page checks below.
        return None
    contract = _require_mapping(raw_contract, field="snapshot")
    if _require_text(contract, "version", field="snapshot") != SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_CONTRACT_VERSION:
        raise ValidationError({"snapshot": "supplier_summary_contract.version must be 1.0."})
    if _require_text(contract, "title", field="snapshot") != "Supplier Monthly Timesheet Summary":
        raise ValidationError({"snapshot": "supplier_summary_contract.title must be 'Supplier Monthly Timesheet Summary'."})
    if _require_text(contract, "scope", field="snapshot") != "supplier_project_period_locked_revision":
        raise ValidationError({"snapshot": "supplier_summary_contract.scope must bind supplier, project, period and locked revision."})
    if _require_text(contract, "row_basis", field="snapshot") != "one_worker_month":
        raise ValidationError({"snapshot": "supplier_summary_contract.row_basis must be one_worker_month."})
    if _require_text(contract, "trade_basis", field="snapshot") != "ordered_distinct_worker_trades":
        raise ValidationError({"snapshot": "supplier_summary_contract.trade_basis must be ordered_distinct_worker_trades."})
    if _require_text(contract, "overtime_basis", field="snapshot") != "monthly_worker_total":
        raise ValidationError({"snapshot": "supplier_summary_contract.overtime_basis must be monthly_worker_total."})
    if contract.get("commercial_values_allowed") is not False:
        raise ValidationError({"snapshot": "supplier_summary_contract.commercial_values_allowed must be false."})

    expected_columns = [
        {"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COLUMNS
    ]
    if contract.get("columns") != expected_columns:
        raise ValidationError({"snapshot": "supplier_summary_contract.columns must use the frozen supplier-facing summary columns."})
    if contract.get("identity_fields") != list(SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_IDENTITY_FIELDS):
        raise ValidationError({"snapshot": "supplier_summary_contract.identity_fields must freeze supplier, project, period and locked revision identity."})
    expected_signatures = [
        {"key": key, "label": label} for key, label in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_SIGNATURE_ROLES
    ]
    if contract.get("signature_roles") != expected_signatures:
        raise ValidationError({"snapshot": "supplier_summary_contract.signature_roles must use the frozen document acknowledgement roles."})
    return contract


def _validate_supplier_summary_rows(
    *,
    data: Mapping[str, Any],
    summary: Mapping[str, Any],
    workers: list[Any],
) -> None:
    rows = data.get("supplier_summary_rows")
    if not isinstance(rows, list):
        raise ValidationError({"snapshot": "supplier_summary_rows must be a list when supplier_summary_contract is present."})
    if len(rows) != len(workers):
        raise ValidationError({"snapshot": "supplier_summary_rows must contain exactly one row per worker."})

    expected_keys = {
        "worker_id",
        "worker_number",
        "worker_name",
        "trades",
        "trade_display",
        *SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COUNT_KEYS,
        "regular_hours",
        "overtime_hours",
        "total_hours",
    }
    aggregate_counts = {key: 0 for key in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COUNT_KEYS}
    aggregate_regular = Decimal("0")
    aggregate_overtime = Decimal("0")

    for index, (raw_row, raw_worker) in enumerate(zip(rows, workers)):
        row = _require_mapping(raw_row, field="snapshot")
        worker = _require_mapping(raw_worker, field="snapshot")
        if set(row.keys()) != expected_keys:
            raise ValidationError({"snapshot": f"supplier_summary_rows[{index}] must contain only the frozen supplier-summary fields."})

        for key in ("worker_id", "worker_number", "worker_name"):
            if _require_text(row, key, field="snapshot") != _require_text(worker, key, field="snapshot"):
                raise ValidationError({"snapshot": f"supplier_summary_rows[{index}].{key} must match workers[{index}].{key}."})

        worker_trades = worker.get("trades")
        if not isinstance(worker_trades, list) or not worker_trades:
            raise ValidationError({"snapshot": f"workers[{index}].trades must contain at least one assigned trade for the supplier summary."})
        if row.get("trades") != worker_trades:
            raise ValidationError({"snapshot": f"supplier_summary_rows[{index}].trades must match workers[{index}].trades."})
        expected_trade_display = " / ".join(str(value).strip() for value in worker_trades)
        if _require_text(row, "trade_display", field="snapshot") != expected_trade_display:
            raise ValidationError({"snapshot": f"supplier_summary_rows[{index}].trade_display must reflect the worker's ordered monthly trades."})

        worker_summary = _require_mapping(worker.get("summary"), field="snapshot")
        for key in SUPPLIER_TIMESHEET_SUPPLIER_SUMMARY_COUNT_KEYS:
            row_value = _require_non_negative_int(row, key, field="snapshot")
            if row_value != _require_non_negative_int(worker_summary, key, field="snapshot"):
                raise ValidationError({"snapshot": f"supplier_summary_rows[{index}].{key} must match the worker monthly-sheet summary."})
            aggregate_counts[key] += row_value

        row_regular = _require_decimal(row, "regular_hours", field="snapshot")
        row_overtime = _require_decimal(row, "overtime_hours", field="snapshot")
        row_total = _require_decimal(row, "total_hours", field="snapshot")
        worker_regular = _require_decimal(worker_summary, "regular_hours", field="snapshot")
        worker_overtime = _require_decimal(worker_summary, "overtime_hours", field="snapshot")
        worker_total = _require_decimal(worker_summary, "total_hours", field="snapshot")
        if (row_regular, row_overtime, row_total) != (worker_regular, worker_overtime, worker_total):
            raise ValidationError({"snapshot": f"supplier_summary_rows[{index}] hours must match the worker monthly-sheet summary."})
        if row_total != row_regular + row_overtime:
            raise ValidationError({"snapshot": f"supplier_summary_rows[{index}].total_hours must equal regular_hours plus overtime_hours."})
        aggregate_regular += row_regular
        aggregate_overtime += row_overtime

    for key, value in aggregate_counts.items():
        if _require_non_negative_int(summary, key, field="snapshot") != value:
            raise ValidationError({"snapshot": f"summary.{key} must reconcile to supplier_summary_rows."})
    if _require_decimal(summary, "regular_hours", field="snapshot") != aggregate_regular:
        raise ValidationError({"snapshot": "summary.regular_hours must reconcile to supplier_summary_rows."})
    if _require_decimal(summary, "overtime_hours", field="snapshot") != aggregate_overtime:
        raise ValidationError({"snapshot": "summary.overtime_hours must reconcile to supplier_summary_rows."})
    if _require_decimal(summary, "total_hours", field="snapshot") != aggregate_regular + aggregate_overtime:
        raise ValidationError({"snapshot": "summary.total_hours must reconcile to supplier_summary_rows."})


def _expected_assignment_segments(days: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_date: date | None = None
    for day in days:
        if str(day.get("assignment_scope") or "").strip() != "assigned":
            current = None
            previous_date = None
            continue
        work_date = date.fromisoformat(str(day.get("date")))
        trade = str(day.get("trade") or "").strip()
        contiguous = previous_date is not None and work_date == previous_date + timedelta(days=1)
        if current is None or not contiguous or current["trade"] != trade:
            current = {"start": work_date.isoformat(), "end": work_date.isoformat(), "trade": trade, "recorded_days": 1}
            result.append(current)
        else:
            current["end"] = work_date.isoformat()
            current["recorded_days"] = int(current["recorded_days"]) + 1
        previous_date = work_date
    return result


def _validate_worker_monthly_sheet(
    *,
    worker_map: Mapping[str, Any],
    worker_summary: Mapping[str, Any],
    days: list[Any],
    worker_index: int,
    period_start: date,
    period_end: date,
) -> None:
    expected_dates: list[date] = []
    cursor = period_start
    while cursor <= period_end:
        expected_dates.append(cursor)
        cursor += timedelta(days=1)

    if len(days) != len(expected_dates):
        raise ValidationError({"snapshot": f"workers[{worker_index}].days must contain every calendar date in the pack period."})

    counts = {key: 0 for key in SUPPLIER_TIMESHEET_WORKER_SHEET_COUNT_KEYS}
    counts["calendar_days"] = len(expected_dates)
    validated_days: list[Mapping[str, Any]] = []
    seen_trades: list[str] = []
    for day_index, (raw_day, expected_date) in enumerate(zip(days, expected_dates)):
        day_map = _require_mapping(raw_day, field="snapshot")
        validated_days.append(day_map)
        day_value = _require_text(day_map, "date", field="snapshot")
        if day_value != expected_date.isoformat():
            raise ValidationError({"snapshot": f"workers[{worker_index}].days must cover the full calendar in exact date order."})
        if _require_text(day_map, "day", field="snapshot") != expected_date.strftime("%A"):
            raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}].day does not match its calendar date."})
        scope = _require_text(day_map, "assignment_scope", field="snapshot")
        code = _require_text(day_map, "attendance_code", field="snapshot")
        attendance = _require_text(day_map, "attendance", field="snapshot")
        regular_hours = _require_decimal(day_map, "regular_hours", field="snapshot")
        trade = str(day_map.get("trade") or "").strip()
        note = str(day_map.get("note") or "").strip()

        if scope == "outside_assignment":
            counts["not_assigned_days"] += 1
            if code != "NOT_ASSIGNED" or attendance != "Not assigned":
                raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}] outside-assignment status is invalid."})
            if regular_hours != Decimal("0") or trade or note:
                raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}] outside-assignment rows cannot fabricate hours, trade or remarks."})
            continue
        if scope != "assigned":
            raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}].assignment_scope must be assigned or outside_assignment."})

        counts["assigned_days"] += 1
        counts["recorded_days"] += 1
        if code not in SUPPLIER_TIMESHEET_WORKER_SHEET_ATTENDANCE:
            raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}].attendance_code is not a supported locked-timesheet status."})
        if attendance != SUPPLIER_TIMESHEET_WORKER_SHEET_ATTENDANCE[code]:
            raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}].attendance does not match attendance_code."})
        if not trade:
            raise ValidationError({"snapshot": f"workers[{worker_index}].days[{day_index}].trade is required for assigned dates."})
        if trade not in seen_trades:
            seen_trades.append(trade)
        if note:
            counts["remark_days"] += 1
        status_key = {
            "WORK": "work_days",
            "A": "absent_days",
            "L": "leave_days",
            "OFF": "off_days",
            "N": "no_scope_days",
        }[code]
        counts[status_key] += 1

    if counts["assigned_days"] < 1:
        raise ValidationError({"snapshot": f"workers[{worker_index}] must contain at least one assigned locked-timesheet day."})
    if counts["recorded_days"] != counts["assigned_days"]:
        raise ValidationError({"snapshot": f"workers[{worker_index}].summary.recorded_days must equal assigned_days for a locked source."})
    if (
        counts["work_days"]
        + counts["absent_days"]
        + counts["leave_days"]
        + counts["off_days"]
        + counts["no_scope_days"]
        != counts["assigned_days"]
    ):
        raise ValidationError({"snapshot": f"workers[{worker_index}] assigned-day attendance counts do not reconcile."})

    for key, actual in counts.items():
        if _require_non_negative_int(worker_summary, key, field="snapshot") != actual:
            raise ValidationError({"snapshot": f"workers[{worker_index}].summary.{key} does not reconcile to the monthly calendar."})

    segments = worker_map.get("assignment_segments")
    if not isinstance(segments, list):
        raise ValidationError({"snapshot": f"workers[{worker_index}].assignment_segments must be a list."})
    expected_segments = _expected_assignment_segments(validated_days)
    if segments != expected_segments:
        raise ValidationError({"snapshot": f"workers[{worker_index}].assignment_segments must match contiguous assigned days and trade changes."})

    trades = worker_map.get("trades")
    if not isinstance(trades, list) or trades != seen_trades:
        raise ValidationError({"snapshot": f"workers[{worker_index}].trades must match the ordered trades recorded on assigned days."})


def validate_supplier_timesheet_pack_snapshot(snapshot: Any) -> None:
    data = _require_mapping(snapshot, field="snapshot")
    if str(data.get("kind") or "").strip() != SUPPLIER_TIMESHEET_PACK_TYPE:
        raise ValidationError({"snapshot": "Supplier Timesheet Pack kind must be 'supplier_timesheet_pack'."})
    if str(data.get("document_schema_version") or "").strip() != SUPPLIER_TIMESHEET_PACK_SCHEMA_VERSION:
        raise ValidationError({"snapshot": "Supplier Timesheet Pack requires document schema version 3.0."})

    period_start = _require_iso_date(data, "period_start", field="snapshot")
    period_end = _require_iso_date(data, "period_end", field="snapshot")
    if period_end < period_start:
        raise ValidationError({"snapshot": "period_end cannot be before period_start."})
    if data.get("revision") in (None, ""):
        raise ValidationError({"snapshot": "revision is required."})
    worker_sheet_contract = _validate_worker_sheet_contract(data)
    supplier_summary_contract = _validate_supplier_summary_contract(data)
    if supplier_summary_contract is not None and worker_sheet_contract is None:
        raise ValidationError({"snapshot": "supplier_summary_contract requires the worker_sheet_contract foundation."})

    project = _require_mapping(data.get("project"), field="snapshot")
    supplier = _require_mapping(data.get("supplier"), field="snapshot")
    source = _require_mapping(data.get("source"), field="snapshot")
    summary = _require_mapping(data.get("summary"), field="snapshot")
    _require_text(project, "code", field="snapshot")
    _require_text(project, "name", field="snapshot")
    _require_text(supplier, "code", field="snapshot")
    _require_text(supplier, "name", field="snapshot")
    source_model = _require_text(source, "model", field="snapshot")
    _require_text(source, "id", field="snapshot")
    if source_model != "rental_manpower.rentaltimesheetperiod":
        raise ValidationError({"snapshot": "Supplier Timesheet Pack source model must be RentalTimesheetPeriod."})
    if str(source.get("status") or "").strip().lower() != "locked":
        raise ValidationError({"snapshot": "Supplier Timesheet Pack source must be a Locked Rental Timesheet."})
    if source.get("revision") in (None, ""):
        raise ValidationError({"snapshot": "Supplier Timesheet Pack source revision is required."})
    if str(source.get("revision")) != str(data.get("revision")):
        raise ValidationError({"snapshot": "Supplier Timesheet Pack revision must match the locked source revision."})

    try:
        worker_count = int(summary.get("worker_count"))
    except (TypeError, ValueError) as exc:
        raise ValidationError({"snapshot": "summary.worker_count must be an integer."}) from exc
    if worker_count < 1:
        raise ValidationError({"snapshot": "summary.worker_count must be at least one."})
    summary_regular = _require_decimal(summary, "regular_hours", field="snapshot")
    summary_overtime = _require_decimal(summary, "overtime_hours", field="snapshot")
    summary_total = _require_decimal(summary, "total_hours", field="snapshot")
    if summary_total != summary_regular + summary_overtime:
        raise ValidationError({"snapshot": "summary.total_hours must equal regular_hours plus overtime_hours."})

    workers = data.get("workers")
    if not isinstance(workers, list):
        raise ValidationError({"snapshot": "workers must be a list."})
    if not workers:
        raise ValidationError({"snapshot": "Supplier Timesheet Pack must contain at least one worker."})
    if worker_count != len(workers):
        raise ValidationError({"snapshot": "summary.worker_count must match the workers collection."})

    seen_worker_ids: set[str] = set()
    seen_worker_numbers: set[str] = set()
    workers_regular = Decimal("0")
    workers_overtime = Decimal("0")
    aggregate_counts = {key: 0 for key in SUPPLIER_TIMESHEET_WORKER_SHEET_COUNT_KEYS}
    for index, worker in enumerate(workers):
        worker_map = _require_mapping(worker, field="snapshot")
        worker_id = _require_text(worker_map, "worker_id", field="snapshot")
        worker_number = _require_text(worker_map, "worker_number", field="snapshot")
        _require_text(worker_map, "worker_name", field="snapshot")
        if worker_id in seen_worker_ids:
            raise ValidationError({"snapshot": f"workers[{index}].worker_id must be unique within the pack."})
        if worker_number in seen_worker_numbers:
            raise ValidationError({"snapshot": f"workers[{index}].worker_number must be unique within the pack."})
        seen_worker_ids.add(worker_id)
        seen_worker_numbers.add(worker_number)

        worker_summary = _require_mapping(worker_map.get("summary"), field="snapshot")
        worker_regular = _require_decimal(worker_summary, "regular_hours", field="snapshot")
        worker_overtime = _require_decimal(worker_summary, "overtime_hours", field="snapshot")
        worker_total = _require_decimal(worker_summary, "total_hours", field="snapshot")
        if worker_total != worker_regular + worker_overtime:
            raise ValidationError({"snapshot": f"workers[{index}].summary.total_hours must equal regular_hours plus overtime_hours."})

        days = worker_map.get("days")
        if not isinstance(days, list):
            raise ValidationError({"snapshot": f"workers[{index}].days must be a list."})
        if not days:
            raise ValidationError({"snapshot": f"workers[{index}].days must contain locked daily attendance rows."})
        seen_dates: set[str] = set()
        day_regular = Decimal("0")
        previous_date: date | None = None
        for day_index, day in enumerate(days):
            day_map = _require_mapping(day, field="snapshot")
            day_value = _require_text(day_map, "date", field="snapshot")
            try:
                work_date = date.fromisoformat(day_value)
            except ValueError as exc:
                raise ValidationError({"snapshot": f"workers[{index}].days[{day_index}].date must use ISO YYYY-MM-DD format."}) from exc
            if not (period_start <= work_date <= period_end):
                raise ValidationError({"snapshot": f"workers[{index}].days[{day_index}].date falls outside the pack period."})
            if day_value in seen_dates:
                raise ValidationError({"snapshot": f"workers[{index}].days contains duplicate date {day_value}."})
            if previous_date is not None and work_date < previous_date:
                raise ValidationError({"snapshot": f"workers[{index}].days must be sorted by date."})
            previous_date = work_date
            seen_dates.add(day_value)
            day_regular += _require_decimal(day_map, "regular_hours", field="snapshot")
            daily_ot = SUPPLIER_TIMESHEET_PACK_DAILY_OT_KEYS.intersection({str(key) for key in day_map})
            if daily_ot:
                raise ValidationError(
                    {"snapshot": f"workers[{index}].days[{day_index}] cannot contain daily overtime; overtime authority is monthly per worker."}
                )
        if day_regular != worker_regular:
            raise ValidationError({"snapshot": f"workers[{index}].summary.regular_hours must equal the sum of daily regular_hours."})

        if worker_sheet_contract is not None:
            _validate_worker_monthly_sheet(
                worker_map=worker_map,
                worker_summary=worker_summary,
                days=days,
                worker_index=index,
                period_start=period_start,
                period_end=period_end,
            )
            for key in aggregate_counts:
                aggregate_counts[key] += _require_non_negative_int(worker_summary, key, field="snapshot")

        workers_regular += worker_regular
        workers_overtime += worker_overtime

    if workers_regular != summary_regular or workers_overtime != summary_overtime:
        raise ValidationError({"snapshot": "Supplier Timesheet Pack summary hours must reconcile to the worker summaries."})

    if worker_sheet_contract is not None:
        for key, expected in aggregate_counts.items():
            if _require_non_negative_int(summary, key, field="snapshot") != expected:
                raise ValidationError({"snapshot": f"summary.{key} must reconcile to the worker monthly-sheet summaries."})

    if supplier_summary_contract is not None:
        _validate_supplier_summary_rows(data=data, summary=summary, workers=workers)

    _walk_forbidden_commercial_fields(data)



def _validate_financial_reconciliation_contract(document_type: str, data: Mapping[str, Any]) -> None:
    contract = data.get("financial_reconciliation_contract")
    # Historical v2 financial documents predate this contract and remain valid forever.
    if contract is None:
        return
    contract = _require_mapping(contract, field="snapshot")
    if _require_text(contract, "version", field="snapshot") != FINANCIAL_RECONCILIATION_CONTRACT_VERSION:
        raise ValidationError({"snapshot": "financial_reconciliation_contract.version is unsupported."})
    if contract.get("timesheet_pack_required") is not False:
        raise ValidationError({"snapshot": "Financial authority must not depend on generating a Supplier Timesheet Pack."})

    normalized = str(document_type or "").strip()
    if normalized in {"supplier_settlement", "supplier_invoice"}:
        if _require_text(contract, "authority", field="snapshot") != "approved_supplier_settlement":
            raise ValidationError({"snapshot": "Settlement and invoice documents must use the approved supplier settlement as financial authority."})
        source_timesheet = _require_mapping(contract.get("source_timesheet"), field="snapshot")
        _require_text(source_timesheet, "id", field="snapshot")
        revision = _require_non_negative_int(source_timesheet, "revision", field="snapshot")
        if revision < 1:
            raise ValidationError({"snapshot": "source_timesheet.revision must be at least 1."})
        if _require_text(source_timesheet, "status", field="snapshot") != "locked":
            raise ValidationError({"snapshot": "Financial documents must remain bound to a Locked source timesheet."})

        settlement = _require_mapping(contract.get("settlement"), field="snapshot")
        _require_text(settlement, "id", field="snapshot")
        if _require_text(settlement, "number", field="snapshot") != _require_text(data, "settlement_number", field="snapshot"):
            raise ValidationError({"snapshot": "financial reconciliation settlement number must match the document snapshot."})
        _require_non_negative_int(settlement, "revision", field="snapshot")
        fingerprint = _require_text(settlement, "snapshot_fingerprint", field="snapshot")
        if len(fingerprint) != 64:
            raise ValidationError({"snapshot": "financial reconciliation settlement fingerprint must be SHA-256."})

        totals = _require_mapping(data.get("totals"), field="snapshot")
        gross = _require_decimal(totals, "gross", field="snapshot")
        earnings = _require_decimal(totals, "adjustment_earnings", field="snapshot")
        deductions = _require_decimal(totals, "adjustment_deductions", field="snapshot")
        net = _require_decimal(totals, "net", field="snapshot")
        if net != gross + earnings - deductions:
            raise ValidationError({"snapshot": "Settlement document totals must preserve the approved settlement net formula."})

        if normalized == "supplier_invoice":
            invoice = _require_mapping(data.get("invoice"), field="snapshot")
            if _require_text(invoice, "match_basis", field="snapshot") != "approved_settlement_net":
                raise ValidationError({"snapshot": "Supplier Invoice Received must match against the approved settlement net."})
            subtotal = _require_decimal(invoice, "subtotal", field="snapshot")
            vat = _require_decimal(invoice, "vat_amount", field="snapshot")
            total = _require_decimal(invoice, "total", field="snapshot")
            settlement_net = _require_decimal(invoice, "settlement_net", field="snapshot")
            subtotal_variance = _require_decimal(invoice, "subtotal_variance", field="snapshot")
            if subtotal != settlement_net or subtotal_variance != Decimal("0"):
                raise ValidationError({"snapshot": "Supplier invoice subtotal must exactly match the approved settlement net."})
            if total != subtotal + vat:
                raise ValidationError({"snapshot": "Supplier invoice total must equal subtotal plus VAT."})
            if _require_text(invoice, "match_status", field="snapshot") != "matched":
                raise ValidationError({"snapshot": "Supplier Invoice Received must be finalized only when matched."})
        return

    if normalized == "supplier_payment_receipt":
        if _require_text(contract, "authority", field="snapshot") != "paid_supplier_payment":
            raise ValidationError({"snapshot": "Payment Advice must use the paid supplier payment as authority."})
        payment = _require_mapping(data.get("payment"), field="snapshot")
        payment_contract = _require_mapping(contract.get("payment"), field="snapshot")
        if _require_text(payment_contract, "number", field="snapshot") != _require_text(payment, "number", field="snapshot"):
            raise ValidationError({"snapshot": "Payment Advice contract must reference the same supplier payment."})
        if _require_text(payment_contract, "status", field="snapshot") != "paid":
            raise ValidationError({"snapshot": "Payment Advice can only represent a Paid supplier payment."})
        amount = _require_decimal(payment, "amount", field="snapshot")
        allocated_total = _require_decimal(contract, "allocated_total", field="snapshot")
        allocations = data.get("allocations")
        if not isinstance(allocations, list) or not allocations:
            raise ValidationError({"snapshot": "Payment Advice must contain at least one settlement allocation."})
        if _require_non_negative_int(contract, "allocation_count", field="snapshot") != len(allocations):
            raise ValidationError({"snapshot": "Payment Advice allocation_count must match allocations."})
        summed = Decimal("0")
        for index, raw in enumerate(allocations):
            row = _require_mapping(raw, field="snapshot")
            _require_text(row, "settlement_number", field="snapshot")
            revision = _require_non_negative_int(row, "source_timesheet_revision", field="snapshot")
            if revision < 1:
                raise ValidationError({"snapshot": f"allocations[{index}].source_timesheet_revision must be at least 1."})
            _require_decimal(row, "settlement_net", field="snapshot")
            summed += _require_decimal(row, "amount", field="snapshot")
            invoice_recorded = row.get("supplier_invoice_recorded")
            if not isinstance(invoice_recorded, bool):
                raise ValidationError({"snapshot": f"allocations[{index}].supplier_invoice_recorded must be boolean."})
            if invoice_recorded:
                _require_text(row, "supplier_invoice_number", field="snapshot")
                _require_decimal(row, "supplier_invoice_total", field="snapshot")
        if summed != allocated_total or allocated_total != amount:
            raise ValidationError({"snapshot": "Payment Advice allocations must reconcile exactly to the paid amount."})
        return

    raise ValidationError({"snapshot": "Unsupported financial reconciliation document type."})

def validate_document_snapshot_for_type(document_type: str, snapshot: Any) -> None:
    normalized = str(document_type or "").strip()
    if normalized == SUPPLIER_TIMESHEET_PACK_TYPE:
        validate_supplier_timesheet_pack_snapshot(snapshot)
    elif normalized in FINANCIAL_RECONCILIATION_DOCUMENT_TYPES:
        data = _require_mapping(snapshot, field="snapshot")
        _validate_financial_reconciliation_contract(normalized, data)
