from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError


ATTENDANCE_WORKSPACE_INTERNAL = "internal"
ATTENDANCE_WORKSPACE_RENTAL = "rental"

ATTENDANCE_STATUS_FLOW = (
    ("draft", "Draft"),
    ("submitted", "Submitted"),
    ("approved", "Approved"),
    ("locked", "Locked"),
)

_ATTENDANCE_CODES = {
    ATTENDANCE_WORKSPACE_INTERNAL: (
        ("A", "Absent", "absent"),
        ("L", "Leave", "leave"),
        ("S", "Sick", "sick"),
        ("H", "Holiday", "holiday"),
        ("OFF", "Off", "off"),
    ),
    ATTENDANCE_WORKSPACE_RENTAL: (
        ("A", "Absent", "absent"),
        ("N", "No Scope", "noscope"),
        ("L", "Leave", "leave"),
        ("OFF", "Off", "off"),
    ),
}

_ATTENDANCE_ALIASES = {
    ATTENDANCE_WORKSPACE_INTERNAL: {
        "P": "8",
        "PRESENT": "8",
        "ABSENT": "A",
        "LEAVE": "L",
        "SICK": "S",
        "SICK LEAVE": "S",
        "HOLIDAY": "H",
        "PUBLIC HOLIDAY": "H",
        "OFFDAY": "OFF",
        "OFF DAY": "OFF",
        "WEEKEND": "OFF",
    },
    ATTENDANCE_WORKSPACE_RENTAL: {
        "P": "8",
        "PRESENT": "8",
        "ABSENT": "A",
        # Rental manpower has no separate sick code. Preserve the existing UI
        # meaning by treating sick/no-work wording as an explicit absent day.
        "SICK": "A",
        "SICK LEAVE": "A",
        "LEAVE": "L",
        "NO SCOPE": "N",
        "NOSCOPE": "N",
        "NO WORK": "N",
        "NOWORK": "N",
        "OFFDAY": "OFF",
        "OFF DAY": "OFF",
        "WEEKEND": "OFF",
    },
}

_WORKFLOW_ACTION_ALIASES = {
    "submit": "submit",
    "submit_review": "submit",
    "submit_for_review": "submit",
    "approve": "approve",
    "lock": "lock",
    "return": "return_to_draft",
    "return_to_draft": "return_to_draft",
    "reject": "return_to_draft",
}


def _workspace_key(workspace: str) -> str:
    value = str(workspace or "").strip().lower()
    if value not in _ATTENDANCE_CODES:
        raise ValueError(f"Unknown payroll attendance workspace: {workspace!r}")
    return value


def attendance_code_values(workspace: str) -> set[str]:
    key = _workspace_key(workspace)
    return {value for value, _label, _tone in _ATTENDANCE_CODES[key]}


def attendance_contract_payload(workspace: str) -> dict[str, object]:
    """JSON-safe contract consumed by forms, imports, validation and the browser.

    Blank is deliberately not a status: it means the required worker/employee-day
    has not been completed. Numeric 0-24 hours and every explicit code below are
    complete values for workflow submission.
    """

    key = _workspace_key(workspace)
    return {
        "workspace": key,
        "minHours": 0,
        "maxHours": 24,
        "hoursPrecision": 2,
        "blankMeansMissing": True,
        "explicitStatusCompletesDay": True,
        "codes": [
            {"value": value, "label": label, "tone": tone}
            for value, label, tone in _ATTENDANCE_CODES[key]
        ],
        "aliases": dict(_ATTENDANCE_ALIASES[key]),
        "workflow": {
            "statuses": [{"value": value, "label": label} for value, label in ATTENDANCE_STATUS_FLOW],
            "nextActions": {"draft": "submit", "submitted": "approve", "approved": "lock", "locked": None},
            "returnAction": "return_to_draft",
        },
    }


def normalize_attendance_workflow_action(action: object) -> str:
    raw = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
    return _WORKFLOW_ACTION_ALIASES.get(raw, raw)


def normalize_payroll_attendance_value(
    value: object,
    *,
    workspace: str,
    field: str = "value",
) -> tuple[Decimal, str, str] | None:
    """Return ``(hours, code, display)`` using the authoritative workspace contract.

    A blank value returns ``None`` and therefore removes/leaves a day missing.
    Text aliases are accepted at the service boundary so imports/API clients do
    not depend on browser-side translation. Numeric values are stored at two
    decimal places and must be finite and between 0 and 24 inclusive.
    """

    key = _workspace_key(workspace)
    raw = str(value if value is not None else "").strip().upper()
    if not raw:
        return None

    raw = _ATTENDANCE_ALIASES[key].get(raw, raw)
    if raw in attendance_code_values(key):
        return Decimal("0"), raw, raw

    try:
        hours = Decimal(raw)
        if not hours.is_finite():
            raise InvalidOperation
        hours = hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter 0–24 hours or a supported attendance status."}) from exc

    if hours < 0 or hours > 24:
        raise ValidationError({field: "Attendance hours must be between 0 and 24."})
    display = format(hours.normalize(), "f") if hours != hours.to_integral() else str(int(hours))
    return hours, "", display
