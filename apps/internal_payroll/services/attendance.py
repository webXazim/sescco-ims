from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.internal_payroll.models import (
    AttendanceCode,
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    AttendancePeriodStatus,
    EmploymentStatus,
    InternalEmployee,
    SalaryStructure,
    SalaryStructureLine,
)

MAX_OVERTIME_HOURS = Decimal("744.00")


def month_bounds(period_start: date) -> tuple[date, date]:
    start = period_start.replace(day=1)
    end = start.replace(day=monthrange(start.year, start.month)[1])
    return start, end


def _require_internal_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot modify internal attendance and overtime.")


def _require_internal_approval(membership: CompanyMembership) -> None:
    if not membership_can_workspace(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot access internal attendance and overtime.")
    if not membership_has_capability(membership, Capability.APPROVE):
        raise PermissionDenied("Your role cannot approve internal attendance and overtime.")


def _decimal(value: object, field: str, places: str = "0.01") -> Decimal:
    try:
        result = Decimal(str(value))
        if not result.is_finite():
            raise InvalidOperation
        return result.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: "Enter a valid finite number."}) from exc


def normalize_attendance_value(value: object) -> tuple[Decimal, str, str] | None:
    """Return (hours, code, normalized display value). Blank means remove/missing."""

    raw = str(value if value is not None else "").strip().upper()
    if not raw:
        return None
    aliases = {
        "P": "8",
        "PRESENT": "8",
        "ABSENT": AttendanceCode.ABSENT,
        "LEAVE": AttendanceCode.LEAVE,
        "SICK": AttendanceCode.SICK,
        "HOLIDAY": AttendanceCode.HOLIDAY,
        "OFFDAY": AttendanceCode.OFF,
        "OFF DAY": AttendanceCode.OFF,
    }
    raw = aliases.get(raw, raw)
    valid_codes = {value for value, _label in AttendanceCode.choices}
    if raw in valid_codes:
        return Decimal("0"), raw, raw
    hours = _decimal(raw, "value")
    if hours < 0 or hours > 24:
        raise ValidationError({"value": "Attendance hours must be between 0 and 24."})
    display = format(hours.normalize(), "f") if hours != hours.to_integral() else str(int(hours))
    return hours, "", display


def _period_snapshot(period: AttendancePeriod) -> dict[str, object]:
    return {
        "period_start": period.period_start.isoformat(),
        "period_end": period.period_end.isoformat(),
        "status": period.status,
        "revision": period.revision,
        "submitted_at": period.submitted_at.isoformat() if period.submitted_at else None,
        "approved_at": period.approved_at.isoformat() if period.approved_at else None,
        "locked_at": period.locked_at.isoformat() if period.locked_at else None,
    }


def _get_or_create_period_locked(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    request: HttpRequest | None = None,
) -> AttendancePeriod:
    company = actor_membership.company
    start, end = month_bounds(period_start)
    period = (
        AttendancePeriod.objects.select_for_update()
        .for_company(company)
        .filter(period_start=start)
        .first()
    )
    if period is not None:
        return period
    period = AttendancePeriod(company=company, period_start=start, period_end=end)
    period.full_clean()
    period.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.attendance_period.created",
        object_type="internal_payroll.AttendancePeriod",
        object_id=period.pk,
        object_label=str(period),
        actor_membership=actor_membership,
        after=_period_snapshot(period),
        request=request,
    )
    return period


def employees_for_attendance_period(*, company, period: AttendancePeriod) -> list[InternalEmployee]:
    return list(
        InternalEmployee.objects.select_for_update()
        .for_company(company)
        .filter(joining_date__lte=period.period_end)
        .filter(Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=period.period_start))
        .exclude(status=EmploymentStatus.INACTIVE)
        .order_by("employee_number", "full_name")
    )


def _employee_required_dates(employee: InternalEmployee, period: AttendancePeriod) -> Iterable[date]:
    current = max(employee.joining_date, period.period_start)
    end = min(employee.employment_end_date or period.period_end, period.period_end)
    while current <= end:
        yield current
        current += timedelta(days=1)


def _attendance_value_snapshot(entry: AttendanceEntry | None) -> object:
    if entry is None:
        return None
    if entry.code:
        return entry.code
    hours = entry.regular_hours
    return format(hours.normalize(), "f") if hours != hours.to_integral() else str(int(hours))


@transaction.atomic
def save_attendance_entries(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    entries: list[dict[str, object]],
    request: HttpRequest | None = None,
) -> AttendancePeriod:
    _require_internal_edit(actor_membership)
    if not isinstance(entries, list) or not entries:
        raise ValidationError({"entries": "At least one attendance entry is required."})
    if len(entries) > 5000:
        raise ValidationError({"entries": "A single attendance save cannot exceed 5,000 entries."})

    company = actor_membership.company
    period = _get_or_create_period_locked(
        actor_membership=actor_membership,
        period_start=period_start,
        request=request,
    )
    if period.status != AttendancePeriodStatus.DRAFT:
        raise ValidationError({"period": "Only Draft attendance periods can be edited."})

    employee_ids = {item.get("employee_id") for item in entries if item.get("employee_id")}
    employees = {
        str(item.pk): item
        for item in InternalEmployee.objects.select_for_update().for_company(company).filter(pk__in=employee_ids)
    }
    if len(employees) != len({str(item) for item in employee_ids}):
        raise ValidationError({"entries": "One or more employees do not belong to the active company."})

    normalized_rows: list[tuple[InternalEmployee, date, tuple[Decimal, str, str] | None, str]] = []
    seen: set[tuple[str, date]] = set()
    for index, item in enumerate(entries):
        employee_id = str(item.get("employee_id") or "")
        employee = employees.get(employee_id)
        if employee is None:
            raise ValidationError({"entries": f"Row {index + 1} has an invalid employee."})
        raw_date = item.get("date")
        if isinstance(raw_date, date):
            work_date = raw_date
        else:
            try:
                work_date = date.fromisoformat(str(raw_date))
            except ValueError as exc:
                raise ValidationError({"entries": f"Row {index + 1} has an invalid date."}) from exc
        key = (employee_id, work_date)
        if key in seen:
            raise ValidationError({"entries": "The same employee/date appears more than once in this save."})
        seen.add(key)
        normalized = normalize_attendance_value(item.get("value"))
        note = str(item.get("note") or "").strip()
        if len(note) > 300:
            raise ValidationError({"entries": f"Row {index + 1} note cannot exceed 300 characters."})
        if not (period.period_start <= work_date <= period.period_end):
            raise ValidationError({"entries": f"{work_date.isoformat()} is outside the attendance period."})
        if work_date < employee.joining_date or (
            employee.employment_end_date and work_date > employee.employment_end_date
        ):
            raise ValidationError({"entries": f"{employee.employee_number} is not employed on {work_date.isoformat()}."})
        normalized_rows.append((employee, work_date, normalized, note))

    existing = {
        (str(item.employee_id), item.work_date): item
        for item in AttendanceEntry.objects.select_for_update()
        .for_company(company)
        .filter(period=period, employee_id__in=employee_ids, work_date__in=[row[1] for row in normalized_rows])
    }
    before_rows: list[dict[str, object]] = []
    after_rows: list[dict[str, object]] = []
    changed = False

    for employee, work_date, normalized, note in normalized_rows:
        key = (str(employee.pk), work_date)
        current = existing.get(key)
        before_value = _attendance_value_snapshot(current)
        before_note = current.note if current else ""
        if normalized is None:
            if current is not None:
                before_rows.append({"employee": employee.employee_number, "date": work_date.isoformat(), "value": before_value, "note": before_note})
                after_rows.append({"employee": employee.employee_number, "date": work_date.isoformat(), "value": None, "note": ""})
                current.delete()
                changed = True
            continue

        hours, code, display = normalized
        if current is None:
            current = AttendanceEntry(
                company=company,
                period=period,
                employee=employee,
                work_date=work_date,
                regular_hours=hours,
                code=code,
                note=note,
            )
        else:
            current.regular_hours = hours
            current.code = code
            current.note = note
        current.full_clean()
        if before_value != display or before_note != note:
            before_rows.append({"employee": employee.employee_number, "date": work_date.isoformat(), "value": before_value, "note": before_note})
            after_rows.append({"employee": employee.employee_number, "date": work_date.isoformat(), "value": display, "note": note})
            current.save()
            changed = True

    if changed:
        period.revision += 1
        period.save(update_fields=("revision", "updated_at"))
        record_audit_event(
            company=company,
            area=AuditArea.INTERNAL,
            action="internal.attendance_entries.saved",
            object_type="internal_payroll.AttendancePeriod",
            object_id=period.pk,
            object_label=str(period),
            actor_membership=actor_membership,
            before={"entries": before_rows},
            after={"entries": after_rows},
            metadata={"changed_count": len(after_rows), "revision": period.revision},
            request=request,
        )
    return period


def _salary_structure_for_overtime(*, company, employee: InternalEmployee, period: AttendancePeriod) -> SalaryStructure:
    structure = (
        SalaryStructure.objects.select_for_update()
        .for_company(company)
        .filter(employee=employee, effective_from__lte=period.period_end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=period.period_end))
        .order_by("-effective_from")
        .first()
    )
    if structure is None:
        raise ValidationError({"overtime": f"{employee.employee_number} has no salary structure effective at the end of this period."})
    if not structure.overtime_policy_name or structure.overtime_divisor is None or structure.overtime_multiplier is None:
        raise ValidationError({"overtime": f"{employee.employee_number} has no overtime policy assigned to the effective salary structure."})
    return structure


def _overtime_calculation(*, company, employee: InternalEmployee, period: AttendancePeriod, hours: Decimal) -> dict[str, object]:
    structure = _salary_structure_for_overtime(company=company, employee=employee, period=period)
    line = (
        SalaryStructureLine.objects.select_for_update()
        .for_company(company)
        .filter(structure=structure, component_code=structure.overtime_base_component_code)
        .first()
    )
    if line is None:
        raise ValidationError({"overtime": f"{employee.employee_number} overtime base component is missing from the effective salary structure."})
    divisor = Decimal(structure.overtime_divisor)
    multiplier = Decimal(structure.overtime_multiplier)
    rate = (line.amount / divisor * multiplier).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    amount = (rate * hours).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "salary_structure": structure,
        "policy_code": structure.overtime_policy_code,
        "policy_name": structure.overtime_policy_name,
        "base_component_code": structure.overtime_base_component_code,
        "base_component_name": structure.overtime_base_component_name,
        "base_amount": line.amount,
        "divisor": divisor,
        "multiplier": multiplier,
        "overtime_rate": rate,
        "amount": amount,
    }


@transaction.atomic
def save_overtime_entries(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    entries: list[dict[str, object]],
    request: HttpRequest | None = None,
) -> AttendancePeriod:
    _require_internal_edit(actor_membership)
    if not isinstance(entries, list) or not entries:
        raise ValidationError({"entries": "At least one overtime entry is required."})
    if len(entries) > 1000:
        raise ValidationError({"entries": "A single overtime save cannot exceed 1,000 employees."})

    company = actor_membership.company
    period = _get_or_create_period_locked(
        actor_membership=actor_membership,
        period_start=period_start,
        request=request,
    )
    if period.status != AttendancePeriodStatus.DRAFT:
        raise ValidationError({"period": "Only Draft attendance periods can be edited."})

    employee_ids = {item.get("employee_id") for item in entries if item.get("employee_id")}
    employees = {
        str(item.pk): item
        for item in InternalEmployee.objects.select_for_update().for_company(company).filter(pk__in=employee_ids)
    }
    if len(employees) != len({str(item) for item in employee_ids}):
        raise ValidationError({"entries": "One or more overtime employees do not belong to the active company."})

    current_rows = {
        str(item.employee_id): item
        for item in AttendanceOvertimeEntry.objects.select_for_update()
        .for_company(company)
        .filter(period=period, employee_id__in=employee_ids)
    }
    before_rows: list[dict[str, object]] = []
    after_rows: list[dict[str, object]] = []
    changed = False

    for index, item in enumerate(entries):
        employee_id = str(item.get("employee_id") or "")
        employee = employees.get(employee_id)
        if employee is None:
            raise ValidationError({"entries": f"Row {index + 1} has an invalid employee."})
        hours = _decimal(item.get("hours", 0), "hours")
        if hours < 0 or hours > MAX_OVERTIME_HOURS:
            raise ValidationError({"hours": f"Overtime hours must be between 0 and {MAX_OVERTIME_HOURS}."})
        current = current_rows.get(employee_id)
        before_signature = None if current is None else (
            current.hours, current.salary_structure_id, current.policy_code, current.policy_name,
            current.base_component_code, current.base_component_name, current.base_amount,
            current.divisor, current.multiplier, current.overtime_rate, current.amount,
        )
        before_rows.append(
            {
                "employee": employee.employee_number,
                "hours": str(current.hours) if current else "0.00",
                "amount": str(current.amount) if current else "0.00",
                "salary_structure_id": str(current.salary_structure_id) if current else None,
                "policy": current.policy_code if current else "",
            }
        )
        if hours == 0:
            if current is not None:
                current.delete()
                changed = True
            after_rows.append({"employee": employee.employee_number, "hours": "0.00", "amount": "0.00"})
            continue

        calculated = _overtime_calculation(company=company, employee=employee, period=period, hours=hours)
        values = {
            "company": company,
            "period": period,
            "employee": employee,
            "hours": hours,
            **calculated,
        }
        if current is None:
            current = AttendanceOvertimeEntry(**values)
        else:
            for field, value in values.items():
                setattr(current, field, value)
        current.full_clean()
        after_signature = (
            current.hours, current.salary_structure_id, current.policy_code, current.policy_name,
            current.base_component_code, current.base_component_name, current.base_amount,
            current.divisor, current.multiplier, current.overtime_rate, current.amount,
        )
        if before_signature != after_signature:
            current.save()
            changed = True
        snapshot_after = {
            "employee": employee.employee_number,
            "hours": str(current.hours),
            "amount": str(current.amount),
            "salary_structure_id": str(current.salary_structure_id),
            "policy": current.policy_code,
        }
        after_rows.append(snapshot_after)

    if changed:
        period.revision += 1
        period.save(update_fields=("revision", "updated_at"))
        record_audit_event(
            company=company,
            area=AuditArea.INTERNAL,
            action="internal.attendance_overtime.saved",
            object_type="internal_payroll.AttendancePeriod",
            object_id=period.pk,
            object_label=str(period),
            actor_membership=actor_membership,
            before={"overtime": before_rows},
            after={"overtime": after_rows},
            metadata={"changed_count": len(after_rows), "revision": period.revision},
            request=request,
        )
    return period


def validate_period_for_submission(*, period: AttendancePeriod) -> None:
    company = period.company
    employees = employees_for_attendance_period(company=company, period=period)
    if not employees:
        raise ValidationError({"period": "No internal employees are employed during this attendance period."})

    entries = {
        (str(item.employee_id), item.work_date): item
        for item in AttendanceEntry.objects.for_company(company).filter(period=period)
    }
    missing: list[str] = []
    for employee in employees:
        for required_date in _employee_required_dates(employee, period):
            if (str(employee.pk), required_date) not in entries:
                missing.append(f"{employee.employee_number} · {required_date.isoformat()}")
                if len(missing) >= 10:
                    break
        if len(missing) >= 10:
            break
    if missing:
        raise ValidationError(
            {
                "attendance": (
                    "Attendance is incomplete. Every employed calendar day must contain hours or an explicit status code. "
                    f"First missing rows: {', '.join(missing)}"
                )
            }
        )

    overtime_rows = list(
        AttendanceOvertimeEntry.objects.select_for_update()
        .for_company(company)
        .filter(period=period)
        .select_related("employee", "salary_structure")
    )
    for row in overtime_rows:
        expected = _overtime_calculation(company=company, employee=row.employee, period=period, hours=row.hours)
        if (
            row.salary_structure_id != expected["salary_structure"].pk
            or row.policy_code != expected["policy_code"]
            or row.base_component_code != expected["base_component_code"]
            or row.base_amount != expected["base_amount"]
            or row.divisor != expected["divisor"]
            or row.multiplier != expected["multiplier"]
            or row.overtime_rate != expected["overtime_rate"]
            or row.amount != expected["amount"]
        ):
            raise ValidationError(
                {"overtime": f"Overtime for {row.employee.employee_number} is stale after a salary change. Save the OT hours again before submission."}
            )


@transaction.atomic
def transition_attendance_period(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    action: str,
    reason: str = "",
    request: HttpRequest | None = None,
) -> AttendancePeriod:
    company = actor_membership.company
    normalized_action = action.strip().lower().replace("-", "_")
    if normalized_action == "submit":
        _require_internal_edit(actor_membership)
    else:
        _require_internal_approval(actor_membership)

    period = _get_or_create_period_locked(
        actor_membership=actor_membership,
        period_start=period_start,
        request=request,
    )
    before = _period_snapshot(period)
    now = timezone.now()

    if normalized_action == "submit":
        if period.status != AttendancePeriodStatus.DRAFT:
            raise ValidationError({"period": "Only a Draft attendance period can be submitted."})
        validate_period_for_submission(period=period)
        period.status = AttendancePeriodStatus.SUBMITTED
        period.submitted_at = now
        period.submitted_by = actor_membership.user
        audit_action = "internal.attendance_period.submitted"
    elif normalized_action == "approve":
        if period.status != AttendancePeriodStatus.SUBMITTED:
            raise ValidationError({"period": "Only a Submitted attendance period can be approved."})
        validate_period_for_submission(period=period)
        period.status = AttendancePeriodStatus.APPROVED
        period.approved_at = now
        period.approved_by = actor_membership.user
        audit_action = "internal.attendance_period.approved"
    elif normalized_action == "lock":
        if period.status != AttendancePeriodStatus.APPROVED:
            raise ValidationError({"period": "Only an Approved attendance period can be locked."})
        validate_period_for_submission(period=period)
        period.status = AttendancePeriodStatus.LOCKED
        period.locked_at = now
        period.locked_by = actor_membership.user
        audit_action = "internal.attendance_period.locked"
    elif normalized_action == "return_to_draft":
        if period.status not in {AttendancePeriodStatus.SUBMITTED, AttendancePeriodStatus.APPROVED, AttendancePeriodStatus.LOCKED}:
            raise ValidationError({"period": "Only Submitted, Approved, or Locked attendance can be returned to Draft."})
        reason = reason.strip()
        if not reason:
            raise ValidationError({"reason": "A return reason is required."})
        # Payroll dependency guard: a calculated/reviewed payroll snapshot must be reset/returned first.
        # Locking the attendance row before checking the payroll run keeps this race-safe.
        from apps.internal_payroll.models import PayrollRun, PayrollRunStatus

        payroll_run = PayrollRun.objects.select_for_update().for_company(company).filter(period_start=period.period_start).first()
        if payroll_run and payroll_run.status != PayrollRunStatus.DRAFT:
            raise ValidationError(
                {"period": f"Attendance cannot be reopened while payroll is {payroll_run.get_status_display()}. Reset the payroll run to Draft first."}
            )
        period.status = AttendancePeriodStatus.DRAFT
        period.submitted_at = None
        period.submitted_by = None
        period.approved_at = None
        period.approved_by = None
        period.locked_at = None
        period.locked_by = None
        audit_action = "internal.attendance_period.returned_to_draft"
    else:
        raise ValidationError({"action": "Action must be submit, approve, lock, or return_to_draft."})

    period.revision += 1
    period.full_clean()
    period.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action=audit_action,
        object_type="internal_payroll.AttendancePeriod",
        object_id=period.pk,
        object_label=str(period),
        actor_membership=actor_membership,
        before=before,
        after=_period_snapshot(period),
        metadata={"reason": reason} if reason else {},
        request=request,
    )
    return period


@transaction.atomic
def import_attendance_rows(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    rows: list[dict[str, object]],
    dry_run: bool = False,
    request: HttpRequest | None = None,
) -> dict[str, object]:
    _require_internal_edit(actor_membership)
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"rows": "Import must contain at least one employee row."})
    if len(rows) > 1000:
        raise ValidationError({"rows": "An attendance import cannot exceed 1,000 employee rows."})

    company = actor_membership.company
    start, end = month_bounds(period_start)
    employees_by_number = {
        item.employee_number.upper(): item
        for item in InternalEmployee.objects.select_for_update().for_company(company).filter(joining_date__lte=end)
    }
    staged: list[dict[str, object]] = []
    seen_employee_numbers: set[str] = set()
    errors: list[str] = []

    for row_index, row in enumerate(rows, start=1):
        employee_number = str(row.get("employee_number") or row.get("employeeId") or "").strip().upper()
        if not employee_number:
            errors.append(f"Row {row_index}: employee number is required.")
            continue
        if employee_number in seen_employee_numbers:
            errors.append(f"Row {row_index}: employee {employee_number} appears more than once.")
            continue
        seen_employee_numbers.add(employee_number)
        employee = employees_by_number.get(employee_number)
        if employee is None:
            errors.append(f"Row {row_index}: employee {employee_number} was not found in the active company.")
            continue
        days = row.get("days")
        if not isinstance(days, dict):
            errors.append(f"Row {row_index}: days must be an object keyed by day number.")
            continue
        for raw_day, value in days.items():
            try:
                day = int(raw_day)
                work_date = start.replace(day=day)
            except (TypeError, ValueError):
                errors.append(f"Row {row_index}: invalid day {raw_day}.")
                continue
            if work_date > end:
                errors.append(f"Row {row_index}: day {day} is outside the month.")
                continue
            try:
                normalize_attendance_value(value)
            except ValidationError as exc:
                errors.append(f"Row {row_index}, day {day}: {exc.messages[0]}")
                continue
            staged.append({"employee_id": str(employee.pk), "date": work_date.isoformat(), "value": value})

    if errors:
        raise ValidationError({"rows": errors[:100]})
    if not staged:
        raise ValidationError({"rows": "Import did not contain any attendance values."})

    if dry_run:
        return {"valid": True, "employee_count": len(seen_employee_numbers), "entry_count": len(staged)}

    period = save_attendance_entries(
        actor_membership=actor_membership,
        period_start=start,
        entries=staged,
        request=request,
    )
    return {
        "valid": True,
        "employee_count": len(seen_employee_numbers),
        "entry_count": len(staged),
        "period_id": str(period.pk),
    }
