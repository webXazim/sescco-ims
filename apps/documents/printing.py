from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

from django.core.exceptions import ValidationError

from .schema import validate_supplier_timesheet_pack_snapshot


SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE = 18


def _chunk(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if size < 1:
        raise ValueError("Chunk size must be positive.")
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def _date_label(value: str) -> str:
    return date.fromisoformat(value).strftime("%d %b %Y")


def _period_label(start: str, end: str) -> str:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date.year == end_date.year and start_date.month == end_date.month:
        return start_date.strftime("%B %Y")
    return f"{start_date:%d %b %Y} – {end_date:%d %b %Y}"


def _signature_roles(value: Mapping[str, Any] | None) -> list[dict[str, str]]:
    roles = list((value or {}).get("signature_roles") or [])
    return [
        {"key": str(row.get("key") or ""), "label": str(row.get("label") or "").strip()}
        for row in roles
        if isinstance(row, Mapping) and str(row.get("label") or "").strip()
    ]


def _worker_print_page(worker: Mapping[str, Any], *, period_label: str) -> dict[str, Any]:
    days: list[dict[str, Any]] = []
    for raw_day in worker.get("days") or []:
        day = dict(raw_day)
        day["date_label"] = _date_label(str(day["date"]))
        day["is_outside_assignment"] = str(day.get("assignment_scope") or "") != "assigned"
        days.append(day)

    segments: list[dict[str, Any]] = []
    for raw_segment in worker.get("assignment_segments") or []:
        segment = dict(raw_segment)
        segment["start_label"] = _date_label(str(segment["start"]))
        segment["end_label"] = _date_label(str(segment["end"]))
        segments.append(segment)

    return {
        "worker_id": str(worker.get("worker_id") or ""),
        "worker_number": str(worker.get("worker_number") or ""),
        "worker_name": str(worker.get("worker_name") or ""),
        "trade_display": " / ".join(str(item) for item in (worker.get("trades") or []) if str(item).strip()),
        "period_label": period_label,
        "summary": dict(worker.get("summary") or {}),
        "assignment_segments": segments,
        "days": days,
    }



class SupplierTimesheetPackWorkerNotFound(LookupError):
    """Requested worker is not present in the immutable Supplier Timesheet Pack snapshot."""


def build_supplier_timesheet_pack_worker_print_context(
    snapshot: Mapping[str, Any],
    *,
    worker_id: object,
) -> dict[str, Any]:
    """Build one derived worker-month print view from a finalized pack snapshot.

    This does not create or mutate a BusinessDocument. The complete parent snapshot is
    validated first, then exactly one worker is selected by its frozen snapshot identity.
    Rendering remains query-free and therefore cannot drift from the finalized pack.
    """

    if not isinstance(snapshot, Mapping):
        raise ValidationError({"snapshot": "Supplier Timesheet Pack snapshot must be an object."})
    validate_supplier_timesheet_pack_snapshot(snapshot)

    normalized_worker_id = str(worker_id or "").strip().lower()
    selected: Mapping[str, Any] | None = None
    for raw_worker in snapshot.get("workers") or []:
        if str(raw_worker.get("worker_id") or "").strip().lower() == normalized_worker_id:
            selected = raw_worker
            break
    if selected is None:
        raise SupplierTimesheetPackWorkerNotFound(normalized_worker_id)

    period_start = str(snapshot["period_start"])
    period_end = str(snapshot["period_end"])
    period_label = _period_label(period_start, period_end)
    source = dict(snapshot.get("source") or {})
    locked_at = str(source.get("locked_at") or "")
    if locked_at:
        source["locked_at_label"] = locked_at.replace("T", " ")[:19]

    return {
        "period_label": period_label,
        "period_start": period_start,
        "period_end": period_end,
        "project": dict(snapshot.get("project") or {}),
        "supplier": dict(snapshot.get("supplier") or {}),
        "source": source,
        "issuer": dict(snapshot.get("issuer") or {}),
        "worker": _worker_print_page(selected, period_label=period_label),
        "worker_signature_roles": _signature_roles(snapshot.get("worker_sheet_contract")),
        "monthly_ot_note": (
            "Overtime is an approved monthly worker total. It is intentionally not allocated to individual dates."
        ),
        "commercial_exclusion_note": (
            "Operational timesheet evidence only. Rates, VAT, settlement amounts and payable values are excluded."
        ),
        "derived_from_pack": True,
    }

def build_supplier_timesheet_pack_print_context(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Prepare an immutable Supplier Timesheet Pack snapshot for A4 printing.

    Rendering is intentionally query-free. The finalized snapshot is validated first,
    supplier summary rows are split into predictable A4-sized sections, and each worker
    becomes one independent render unit. A worker table is allowed to flow onto a second
    physical page if unusually long remarks require it; the template never clips rows.
    """

    if not isinstance(snapshot, Mapping):
        raise ValidationError({"snapshot": "Supplier Timesheet Pack snapshot must be an object."})
    validate_supplier_timesheet_pack_snapshot(snapshot)

    summary_rows = [dict(row) for row in snapshot.get("supplier_summary_rows") or []]
    chunks = _chunk(summary_rows, SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE)
    if not chunks:
        raise ValidationError({"snapshot": "Supplier Timesheet Pack summary cannot be empty."})

    period_start = str(snapshot["period_start"])
    period_end = str(snapshot["period_end"])
    period_label = _period_label(period_start, period_end)
    summary_signatures = _signature_roles(snapshot.get("supplier_summary_contract"))
    worker_signatures = _signature_roles(snapshot.get("worker_sheet_contract"))

    summary_pages: list[dict[str, Any]] = []
    for index, rows in enumerate(chunks, start=1):
        summary_pages.append(
            {
                "number": index,
                "count": len(chunks),
                "is_first": index == 1,
                "is_last": index == len(chunks),
                "rows": rows,
                "signature_roles": summary_signatures if index == len(chunks) else [],
            }
        )

    worker_pages = [
        _worker_print_page(worker, period_label=period_label)
        for worker in (snapshot.get("workers") or [])
    ]
    if len(worker_pages) != int((snapshot.get("summary") or {}).get("worker_count") or 0):
        raise ValidationError({"snapshot": "Printable worker-page count does not reconcile with summary.worker_count."})

    source = dict(snapshot.get("source") or {})
    locked_at = str(source.get("locked_at") or "")
    if locked_at:
        source["locked_at_label"] = locked_at.replace("T", " ")[:19]

    return {
        "period_label": period_label,
        "period_start": period_start,
        "period_end": period_end,
        "project": dict(snapshot.get("project") or {}),
        "supplier": dict(snapshot.get("supplier") or {}),
        "summary": dict(snapshot.get("summary") or {}),
        "source": source,
        "issuer": dict(snapshot.get("issuer") or {}),
        "summary_pages": summary_pages,
        "summary_page_count": len(summary_pages),
        "worker_pages": worker_pages,
        "worker_page_count": len(worker_pages),
        "worker_signature_roles": worker_signatures,
        "monthly_ot_note": (
            "Overtime is an approved monthly worker total. It is intentionally not allocated to individual dates."
        ),
        "commercial_exclusion_note": (
            "Operational timesheet evidence only. Rates, VAT, settlement amounts and payable values are excluded."
        ),
    }
