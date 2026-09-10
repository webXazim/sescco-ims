from __future__ import annotations

import hashlib
import json
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, Sum
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
    EmployeeOrganizationAssignment,
    InternalEmployee,
    InternalPayrollPolicy,
    PayrollAdjustment,
    PayrollAdjustmentStatus,
    PayrollAdjustmentType,
    PayrollProrationMethod,
    PayrollRun,
    PayrollRunLine,
    PayrollRunLineAdjustment,
    PayrollRunLineComponent,
    PayrollRunStatus,
    SalaryComponentCategory,
    SalaryStructure,
    SalaryStructureLine,
    WPSMapping,
)
from apps.internal_payroll.services.attendance import employees_for_attendance_period, month_bounds, validate_period_for_submission

MONEY_QUANT = Decimal("0.01")


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _require_internal_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot modify internal payroll.")


def _require_internal_approval(membership: CompanyMembership) -> None:
    if not membership_can_workspace(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot access internal payroll.")
    if not membership_has_capability(membership, Capability.APPROVE):
        raise PermissionDenied("Your role cannot approve internal payroll.")


def _hash_payload(value: object) -> str:
    encoded = json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _period_key(start: date) -> str:
    return f"{start:%Y-%m}"


def _policy_locked(company) -> InternalPayrollPolicy | None:
    return InternalPayrollPolicy.objects.select_for_update().for_company(company).first()


@transaction.atomic
def update_payroll_policy(
    *,
    actor_membership: CompanyMembership,
    proration_method: str,
    request: HttpRequest | None = None,
) -> InternalPayrollPolicy:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    try:
        normalized = PayrollProrationMethod(proration_method).value
    except ValueError as exc:
        raise ValidationError({"proration_method": "Choose a valid payroll proration method."}) from exc

    if PayrollRun.objects.select_for_update().for_company(company).filter(status=PayrollRunStatus.REVIEW).exists():
        raise ValidationError({"policy": "Payroll policy cannot change while a payroll run is in Finance Review."})

    policy = _policy_locked(company)
    before = {"proration_method": policy.proration_method} if policy else {}
    if policy is None:
        policy = InternalPayrollPolicy(company=company, proration_method=normalized)
    else:
        policy.proration_method = normalized
    policy.full_clean()
    policy.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.payroll_policy.updated",
        object_type="internal_payroll.InternalPayrollPolicy",
        object_id=policy.pk,
        object_label=str(policy),
        actor_membership=actor_membership,
        before=before,
        after={"proration_method": policy.proration_method},
        request=request,
    )
    return policy


def _assert_adjustment_period_mutable(*, company, period_start: date) -> None:
    run = PayrollRun.objects.select_for_update().for_company(company).filter(period_start=period_start).first()
    if run and run.status in {
        PayrollRunStatus.REVIEW,
        PayrollRunStatus.APPROVED,
        PayrollRunStatus.PAYMENT_PROCESSING,
        PayrollRunStatus.PAID,
        PayrollRunStatus.CLOSED,
    }:
        raise ValidationError({"period": f"Adjustments are frozen because {_period_key(period_start)} payroll is {run.get_status_display()}."})


def _adjustment_snapshot(adjustment: PayrollAdjustment) -> dict[str, object]:
    return {
        "employee_id": str(adjustment.employee_id),
        "transaction_date": adjustment.transaction_date.isoformat(),
        "period": _period_key(adjustment.period_start),
        "type": adjustment.adjustment_type,
        "amount": str(adjustment.amount),
        "reason": adjustment.reason,
        "reference": adjustment.reference,
        "recovery_plan": adjustment.recovery_plan,
        "installment_amount": str(adjustment.installment_amount) if adjustment.installment_amount is not None else None,
        "recovery_start": adjustment.recovery_start.isoformat() if adjustment.recovery_start else None,
        "status": adjustment.status,
    }


@transaction.atomic
def create_payroll_adjustment(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    transaction_date: date,
    period_start: date,
    adjustment_type: str,
    amount: Decimal,
    reason: str,
    reference: str = "",
    recovery_plan: str = "",
    installment_amount: Decimal | None = None,
    recovery_start: date | None = None,
    request: HttpRequest | None = None,
) -> PayrollAdjustment:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    start, _end = month_bounds(period_start)
    _assert_adjustment_period_mutable(company=company, period_start=start)
    employee = InternalEmployee.objects.select_for_update().for_company(company).filter(pk=employee_id).first()
    if employee is None:
        raise ValidationError({"employee": "Employee does not belong to the active company."})
    if transaction_date < employee.joining_date:
        raise ValidationError({"transaction_date": "Transaction date cannot be before the employee joining date."})
    if employee.employment_end_date and transaction_date > employee.employment_end_date:
        raise ValidationError({"transaction_date": "Transaction date cannot be after the employee employment end date."})
    try:
        normalized_type = PayrollAdjustmentType(adjustment_type).value
    except ValueError as exc:
        raise ValidationError({"adjustment_type": "Choose a valid adjustment type."}) from exc
    adjustment = PayrollAdjustment(
        company=company,
        employee=employee,
        transaction_date=transaction_date,
        period_start=start,
        adjustment_type=normalized_type,
        amount=_money(amount),
        reason=reason,
        reference=reference,
        recovery_plan=recovery_plan,
        installment_amount=_money(installment_amount) if installment_amount is not None else None,
        recovery_start=recovery_start,
        status=PayrollAdjustmentStatus.DRAFT,
    )
    adjustment.full_clean()
    adjustment.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.payroll_adjustment.created",
        object_type="internal_payroll.PayrollAdjustment",
        object_id=adjustment.pk,
        object_label=str(adjustment),
        actor_membership=actor_membership,
        after=_adjustment_snapshot(adjustment),
        request=request,
    )
    return adjustment


@transaction.atomic
def update_payroll_adjustment(
    *,
    actor_membership: CompanyMembership,
    adjustment_id,
    values: dict[str, object],
    request: HttpRequest | None = None,
) -> PayrollAdjustment:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    adjustment = (
        PayrollAdjustment.objects.select_for_update().for_company(company).select_related("employee").filter(pk=adjustment_id).first()
    )
    if adjustment is None:
        raise ValidationError({"adjustment": "Adjustment does not belong to the active company."})
    if adjustment.status != PayrollAdjustmentStatus.DRAFT:
        raise ValidationError({"adjustment": "Only Draft adjustments can be edited."})
    _assert_adjustment_period_mutable(company=company, period_start=adjustment.period_start)
    before = _adjustment_snapshot(adjustment)

    if "transaction_date" in values:
        adjustment.transaction_date = values["transaction_date"]  # type: ignore[assignment]
    if "period_start" in values:
        next_start, _end = month_bounds(values["period_start"])  # type: ignore[arg-type]
        _assert_adjustment_period_mutable(company=company, period_start=next_start)
        adjustment.period_start = next_start
    if "adjustment_type" in values:
        try:
            adjustment.adjustment_type = PayrollAdjustmentType(str(values["adjustment_type"])).value
        except ValueError as exc:
            raise ValidationError({"adjustment_type": "Choose a valid adjustment type."}) from exc
    if "amount" in values:
        adjustment.amount = _money(values["amount"])  # type: ignore[arg-type]
    for field in ("reason", "reference", "recovery_plan"):
        if field in values:
            setattr(adjustment, field, str(values[field] or ""))
    if "installment_amount" in values:
        raw = values["installment_amount"]
        adjustment.installment_amount = None if raw in (None, "") else _money(raw)  # type: ignore[arg-type]
    if "recovery_start" in values:
        adjustment.recovery_start = values["recovery_start"]  # type: ignore[assignment]

    if adjustment.transaction_date < adjustment.employee.joining_date:
        raise ValidationError({"transaction_date": "Transaction date cannot be before the employee joining date."})
    if adjustment.employee.employment_end_date and adjustment.transaction_date > adjustment.employee.employment_end_date:
        raise ValidationError({"transaction_date": "Transaction date cannot be after the employee employment end date."})
    adjustment.full_clean()
    adjustment.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.payroll_adjustment.updated",
        object_type="internal_payroll.PayrollAdjustment",
        object_id=adjustment.pk,
        object_label=str(adjustment),
        actor_membership=actor_membership,
        before=before,
        after=_adjustment_snapshot(adjustment),
        request=request,
    )
    return adjustment


def _approved_advance_balance_locked(
    *, company, employee: InternalEmployee, as_of: date, exclude_adjustment_id=None
) -> Decimal:
    rows = PayrollAdjustment.objects.select_for_update().for_company(company).filter(
        employee=employee,
        status=PayrollAdjustmentStatus.APPROVED,
        transaction_date__lte=as_of,
        adjustment_type__in=[PayrollAdjustmentType.SALARY_ADVANCE, PayrollAdjustmentType.ADVANCE_RECOVERY],
    )
    if exclude_adjustment_id:
        rows = rows.exclude(pk=exclude_adjustment_id)
    issued = rows.filter(adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    recovered = rows.filter(adjustment_type=PayrollAdjustmentType.ADVANCE_RECOVERY).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return _money(issued - recovered)


@transaction.atomic
def transition_payroll_adjustment(
    *,
    actor_membership: CompanyMembership,
    adjustment_id,
    action: str,
    reason: str = "",
    request: HttpRequest | None = None,
) -> PayrollAdjustment:
    company = actor_membership.company
    normalized = action.strip().lower().replace("-", "_")
    if normalized == "submit":
        _require_internal_edit(actor_membership)
    else:
        _require_internal_approval(actor_membership)
    adjustment = (
        PayrollAdjustment.objects.select_for_update().for_company(company).select_related("employee").filter(pk=adjustment_id).first()
    )
    if adjustment is None:
        raise ValidationError({"adjustment": "Adjustment does not belong to the active company."})
    _assert_adjustment_period_mutable(company=company, period_start=adjustment.period_start)
    before = _adjustment_snapshot(adjustment)
    now = timezone.now()

    if normalized == "submit":
        if adjustment.status != PayrollAdjustmentStatus.DRAFT:
            raise ValidationError({"adjustment": "Only a Draft adjustment can be submitted."})
        adjustment.status = PayrollAdjustmentStatus.REVIEW
        adjustment.submitted_at = now
        adjustment.submitted_by = actor_membership.user
        audit_action = "internal.payroll_adjustment.submitted"
    elif normalized == "approve":
        if adjustment.status != PayrollAdjustmentStatus.REVIEW:
            raise ValidationError({"adjustment": "Only an adjustment in Review can be approved."})
        InternalEmployee.objects.select_for_update().for_company(company).get(pk=adjustment.employee_id)
        if adjustment.adjustment_type == PayrollAdjustmentType.ADVANCE_RECOVERY:
            balance = _approved_advance_balance_locked(
                company=company,
                employee=adjustment.employee,
                as_of=adjustment.transaction_date,
                exclude_adjustment_id=adjustment.pk,
            )
            if adjustment.amount > balance:
                raise ValidationError({"amount": f"Advance recovery exceeds the approved outstanding balance ({balance:.2f})."})
        adjustment.status = PayrollAdjustmentStatus.APPROVED
        adjustment.approved_at = now
        adjustment.approved_by = actor_membership.user
        audit_action = "internal.payroll_adjustment.approved"
    elif normalized == "return_to_draft":
        if adjustment.status != PayrollAdjustmentStatus.REVIEW:
            raise ValidationError({"adjustment": "Only an adjustment in Review can be returned to Draft."})
        reason = reason.strip()
        if not reason:
            raise ValidationError({"reason": "A return reason is required."})
        adjustment.status = PayrollAdjustmentStatus.DRAFT
        adjustment.submitted_at = None
        adjustment.submitted_by = None
        audit_action = "internal.payroll_adjustment.returned_to_draft"
    else:
        raise ValidationError({"action": "Unsupported adjustment workflow action."})

    adjustment.full_clean()
    adjustment.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action=audit_action,
        object_type="internal_payroll.PayrollAdjustment",
        object_id=adjustment.pk,
        object_label=str(adjustment),
        actor_membership=actor_membership,
        before=before,
        after=_adjustment_snapshot(adjustment),
        metadata={"reason": reason} if reason else {},
        request=request,
    )
    return adjustment


def _organization_as_of_locked(*, company, employee: InternalEmployee, as_of: date) -> EmployeeOrganizationAssignment | None:
    return (
        EmployeeOrganizationAssignment.objects.select_for_update().for_company(company)
        .select_related("branch", "department")
        .filter(employee=employee, effective_from__lte=as_of)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
        .order_by("-effective_from", "-created_at")
        .first()
    )


def _structure_lines_locked(*, company, structure: SalaryStructure) -> list[SalaryStructureLine]:
    return list(
        SalaryStructureLine.objects.select_for_update().for_company(company)
        .filter(structure=structure)
        .select_related("component")
        .order_by("component_category", "component_code")
    )


def _overlapping_structures_locked(*, company, employee: InternalEmployee, start: date, end: date) -> list[SalaryStructure]:
    return list(
        SalaryStructure.objects.select_for_update().for_company(company)
        .filter(employee=employee, effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
        .order_by("effective_from", "created_at")
    )


def _component_contributions(
    *,
    company,
    employee: InternalEmployee,
    period_start: date,
    period_end: date,
    proration_method: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    employed_start = max(period_start, employee.joining_date)
    employed_end = min(period_end, employee.employment_end_date or period_end)
    structures = _overlapping_structures_locked(company=company, employee=employee, start=employed_start, end=employed_end)
    blockers: list[str] = []
    if not structures:
        return [], ["No salary structure covers the employee's payroll period."]

    partial_employment = employed_start != period_start or employed_end != period_end
    salary_change_in_period = len(structures) > 1 or structures[0].effective_from > employed_start or (
        structures[0].effective_to is not None and structures[0].effective_to < employed_end
    )
    ambiguous = partial_employment or salary_change_in_period
    if ambiguous and proration_method == PayrollProrationMethod.NOT_CONFIGURED:
        return [], ["Payroll proration must be configured for partial-month employment or a salary change inside the period."]

    contributions: list[dict[str, Any]] = []
    if proration_method in {PayrollProrationMethod.NOT_CONFIGURED, PayrollProrationMethod.NO_PRORATION}:
        reference_date = employed_end
        structure = next(
            (
                item for item in reversed(structures)
                if item.effective_from <= reference_date and (item.effective_to is None or item.effective_to >= reference_date)
            ),
            None,
        )
        if structure is None:
            return [], ["No salary structure is effective on the employee's payroll reference date."]
        for line in _structure_lines_locked(company=company, structure=structure):
            contributions.append(
                {
                    "structure": structure,
                    "line": line,
                    "effective_from": employed_start,
                    "effective_to": employed_end,
                    "proration_days": (employed_end - employed_start).days + 1,
                    "proration_denominator": (employed_end - employed_start).days + 1,
                    "amount": _money(line.amount),
                }
            )
        return contributions, blockers

    denominator = monthrange(period_start.year, period_start.month)[1]
    cursor = employed_start
    for structure in structures:
        seg_start = max(cursor, employed_start, structure.effective_from)
        seg_end = min(employed_end, structure.effective_to or employed_end)
        if seg_end < seg_start:
            continue
        if seg_start > cursor:
            blockers.append(f"Salary structure coverage is missing from {cursor.isoformat()} to {(seg_start - timedelta(days=1)).isoformat()}.")
            break
        days = (seg_end - seg_start).days + 1
        for line in _structure_lines_locked(company=company, structure=structure):
            contributions.append(
                {
                    "structure": structure,
                    "line": line,
                    "effective_from": seg_start,
                    "effective_to": seg_end,
                    "proration_days": days,
                    "proration_denominator": denominator,
                    "amount": _money(line.amount * Decimal(days) / Decimal(denominator)),
                }
            )
        cursor = seg_end + timedelta(days=1)
        if cursor > employed_end:
            break
    if cursor <= employed_end and not blockers:
        blockers.append(f"Salary structure coverage is missing from {cursor.isoformat()} to {employed_end.isoformat()}.")
    return contributions, blockers


def _attendance_summary_locked(*, company, period: AttendancePeriod, employee: InternalEmployee) -> dict[str, Any]:
    entries = list(
        AttendanceEntry.objects.select_for_update().for_company(company)
        .filter(period=period, employee=employee)
        .order_by("work_date")
    )
    summary = {
        "regular_hours": sum((item.regular_hours for item in entries), Decimal("0")),
        "absent_days": 0,
        "leave_days": 0,
        "sick_days": 0,
        "holiday_days": 0,
        "off_days": 0,
        "source_entries": [
            {
                "date": item.work_date.isoformat(),
                "regular_hours": str(item.regular_hours),
                "code": item.code,
            }
            for item in entries
        ],
    }
    code_fields = {
        AttendanceCode.ABSENT: "absent_days",
        AttendanceCode.LEAVE: "leave_days",
        AttendanceCode.SICK: "sick_days",
        AttendanceCode.HOLIDAY: "holiday_days",
        AttendanceCode.OFF: "off_days",
    }
    for item in entries:
        if item.code:
            summary[code_fields[item.code]] += 1
    overtime = (
        AttendanceOvertimeEntry.objects.select_for_update().for_company(company)
        .filter(period=period, employee=employee)
        .select_related("salary_structure")
        .first()
    )
    summary["overtime"] = overtime
    return summary


def _adjustment_effect(adjustment_type: str) -> str | None:
    if adjustment_type in {PayrollAdjustmentType.BONUS, PayrollAdjustmentType.REIMBURSEMENT, PayrollAdjustmentType.OTHER_EARNING}:
        return "earning"
    if adjustment_type == PayrollAdjustmentType.ADVANCE_RECOVERY:
        return "advance_recovery"
    if adjustment_type in {PayrollAdjustmentType.FINE, PayrollAdjustmentType.OTHER_DEDUCTION}:
        return "deduction"
    return None


def _build_calculation_locked(*, company, period_start: date) -> dict[str, Any]:
    start, end = month_bounds(period_start)
    attendance = (
        # Lock only the attendance-period row. The workflow user relations are
        # nullable, so PostgreSQL renders them as LEFT OUTER JOINs; an
        # unrestricted FOR UPDATE would incorrectly try to lock the nullable
        # side of those joins and raise NotSupportedError.
        AttendancePeriod.objects.select_for_update(of=("self",)).for_company(company)
        .filter(period_start=start)
        .select_related("submitted_by", "approved_by", "locked_by")
        .first()
    )
    if attendance is None:
        raise ValidationError({"attendance": "Attendance period does not exist for this payroll month."})
    if attendance.status not in {AttendancePeriodStatus.APPROVED, AttendancePeriodStatus.LOCKED}:
        raise ValidationError({"attendance": "Payroll calculation requires Approved or Locked attendance."})
    validate_period_for_submission(period=attendance)

    policy = _policy_locked(company)
    proration_method = policy.proration_method if policy else PayrollProrationMethod.NOT_CONFIGURED
    employees = employees_for_attendance_period(company=company, period=attendance)
    if not employees:
        raise ValidationError({"payroll": "No internal employees are employed during this payroll period."})

    adjustments = list(
        PayrollAdjustment.objects.select_for_update().for_company(company)
        .filter(period_start=start, status=PayrollAdjustmentStatus.APPROVED)
        .select_related("employee")
        .order_by("employee__employee_number", "transaction_date", "created_at")
    )
    adjustments_by_employee: dict[str, list[PayrollAdjustment]] = {}
    for item in adjustments:
        adjustments_by_employee.setdefault(str(item.employee_id), []).append(item)

    result_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    blockers: list[str] = []

    for employee in employees:
        emp_blockers: list[str] = []
        reference_date = min(end, employee.employment_end_date or end)
        organization = _organization_as_of_locked(company=company, employee=employee, as_of=reference_date)
        if organization is None:
            emp_blockers.append("No branch/department assignment covers the payroll reference date.")

        contributions, salary_blockers = _component_contributions(
            company=company,
            employee=employee,
            period_start=start,
            period_end=end,
            proration_method=proration_method,
        )
        emp_blockers.extend(salary_blockers)
        attendance_summary = _attendance_summary_locked(company=company, period=attendance, employee=employee)
        overtime = attendance_summary["overtime"]

        basic = Decimal("0")
        allowances = Decimal("0")
        recurring_other = Decimal("0")
        salary_deductions = Decimal("0")
        component_payload: list[dict[str, Any]] = []
        for item in contributions:
            line: SalaryStructureLine = item["line"]
            amount: Decimal = item["amount"]
            if line.component_category == SalaryComponentCategory.EARNING:
                if line.wps_mapping == WPSMapping.BASIC_SALARY:
                    basic += amount
                elif line.wps_mapping == WPSMapping.OTHER_EARNINGS:
                    recurring_other += amount
                else:
                    allowances += amount
            else:
                salary_deductions += amount
            component_payload.append(item)
        basic = _money(basic)
        allowances = _money(allowances)
        recurring_other = _money(recurring_other)
        salary_deductions = _money(salary_deductions)
        if basic <= Decimal("0"):
            emp_blockers.append("Basic Salary must calculate to an amount greater than zero.")

        overtime_amount = _money(overtime.amount if overtime else Decimal("0"))
        overtime_hours = overtime.hours if overtime else Decimal("0")
        adjustment_earnings = Decimal("0")
        advance_recovery = Decimal("0")
        other_adjustment_deductions = Decimal("0")
        adjustment_payload: list[dict[str, Any]] = []
        for adjustment in adjustments_by_employee.get(str(employee.pk), []):
            effect = _adjustment_effect(adjustment.adjustment_type)
            if effect is None:
                continue  # Salary Advance creates a balance; it is not a payroll deduction until a recovery is approved.
            if effect == "earning":
                adjustment_earnings += adjustment.amount
            elif effect == "advance_recovery":
                advance_recovery += adjustment.amount
            else:
                other_adjustment_deductions += adjustment.amount
            adjustment_payload.append({"adjustment": adjustment, "effect": effect})

        other_earnings = _money(recurring_other + adjustment_earnings)
        other_deductions = _money(salary_deductions + other_adjustment_deductions)
        gross = _money(basic + allowances + overtime_amount + other_earnings)
        total_deductions = _money(advance_recovery + other_deductions)
        if total_deductions > gross:
            emp_blockers.append("Payroll deductions exceed gross earnings; reduce or reschedule deductions before calculation.")
        net = _money(max(Decimal("0"), gross - total_deductions))

        if emp_blockers:
            blockers.extend(f"{employee.employee_number} · {message}" for message in emp_blockers)

        source_row = {
            "employee_id": str(employee.pk),
            "employee_number": employee.employee_number,
            "joining_date": employee.joining_date.isoformat(),
            "employment_end_date": employee.employment_end_date.isoformat() if employee.employment_end_date else None,
            "organization_id": str(organization.pk) if organization else None,
            "attendance": attendance_summary["source_entries"],
            "components": [
                {
                    "structure_id": str(item["structure"].pk),
                    "line_id": str(item["line"].pk),
                    "base_amount": str(item["line"].amount),
                    "effective_from": item["effective_from"].isoformat(),
                    "effective_to": item["effective_to"].isoformat(),
                    "days": item["proration_days"],
                    "denominator": item["proration_denominator"],
                    "amount": str(item["amount"]),
                }
                for item in component_payload
            ],
            "overtime": None if overtime is None else {
                "id": str(overtime.pk),
                "hours": str(overtime.hours),
                "amount": str(overtime.amount),
                "salary_structure_id": str(overtime.salary_structure_id),
                "policy_code": overtime.policy_code,
                "rate": str(overtime.overtime_rate),
            },
            "adjustments": [
                {
                    "id": str(item["adjustment"].pk),
                    "type": item["adjustment"].adjustment_type,
                    "amount": str(item["adjustment"].amount),
                    "status": item["adjustment"].status,
                    "effect": item["effect"],
                }
                for item in adjustment_payload
            ],
        }
        source_rows.append(source_row)
        result_rows.append(
            {
                "employee": employee,
                "organization": organization,
                "components": component_payload,
                "adjustments": adjustment_payload,
                "regular_hours": attendance_summary["regular_hours"],
                "absent_days": attendance_summary["absent_days"],
                "leave_days": attendance_summary["leave_days"],
                "sick_days": attendance_summary["sick_days"],
                "holiday_days": attendance_summary["holiday_days"],
                "off_days": attendance_summary["off_days"],
                "overtime": overtime,
                "overtime_hours": overtime_hours,
                "overtime_amount": overtime_amount,
                "basic": basic,
                "allowances": allowances,
                "other_earnings": other_earnings,
                "gross": gross,
                "advance_recovery": _money(advance_recovery),
                "other_deductions": other_deductions,
                "total_deductions": total_deductions,
                "net": net,
                "blockers": emp_blockers,
            }
        )

    source = {
        "calculation_version": 1,
        "period": _period_key(start),
        "attendance_id": str(attendance.pk),
        "proration_method": proration_method,
        "rows": source_rows,
    }
    return {
        "period_start": start,
        "period_end": end,
        "attendance": attendance,
        "policy": policy,
        "proration_method": proration_method,
        "rows": result_rows,
        "blockers": blockers,
        "source_fingerprint": _hash_payload(source),
    }


def _snapshot_payload_locked(*, run: PayrollRun) -> dict[str, Any]:
    """Return the complete persisted payroll snapshot used for integrity verification."""

    rows = list(
        PayrollRunLine.objects.select_for_update().for_company(run.company)
        .filter(run=run)
        .order_by("employee_number", "id")
    )
    payload_rows: list[dict[str, Any]] = []
    for row in rows:
        components = list(
            PayrollRunLineComponent.objects.select_for_update().for_company(run.company)
            .filter(run_line=row)
            .order_by("component_code", "effective_from", "id")
        )
        adjustments = list(
            PayrollRunLineAdjustment.objects.select_for_update().for_company(run.company)
            .filter(run_line=row)
            .order_by("transaction_date", "id")
        )
        payload_rows.append(
            {
                "employee_id": str(row.employee_id),
                "employee_number": row.employee_number,
                "employee_name": row.employee_name,
                "branch_id": str(row.branch_id_snapshot) if row.branch_id_snapshot else None,
                "branch_code": row.branch_code,
                "branch_name": row.branch_name,
                "department_id": str(row.department_id_snapshot) if row.department_id_snapshot else None,
                "department_code": row.department_code,
                "department_name": row.department_name,
                "position": row.position,
                "regular_hours": str(row.regular_hours),
                "absent_days": row.absent_days,
                "leave_days": row.leave_days,
                "sick_days": row.sick_days,
                "holiday_days": row.holiday_days,
                "off_days": row.off_days,
                "overtime_hours": str(row.overtime_hours),
                "overtime_amount": str(row.overtime_amount),
                "overtime_policy_code": row.overtime_policy_code,
                "overtime_policy_name": row.overtime_policy_name,
                "overtime_rate": str(row.overtime_rate) if row.overtime_rate is not None else None,
                "basic": str(row.basic),
                "allowances": str(row.allowances),
                "other_earnings": str(row.other_earnings),
                "gross": str(row.gross),
                "advance_recovery": str(row.advance_recovery),
                "other_deductions": str(row.other_deductions),
                "total_deductions": str(row.total_deductions),
                "net": str(row.net),
                "components": [
                    {
                        "salary_structure_id": str(item.salary_structure_id),
                        "line_id": str(item.salary_structure_line_id),
                        "code": item.component_code,
                        "name": item.component_name,
                        "category": item.component_category,
                        "recurrence": item.component_recurrence,
                        "calculation": item.component_calculation,
                        "wps_mapping": item.wps_mapping,
                        "base": str(item.base_amount),
                        "from": item.effective_from.isoformat(),
                        "to": item.effective_to.isoformat(),
                        "days": item.proration_days,
                        "denom": item.proration_denominator,
                        "amount": str(item.amount),
                    }
                    for item in components
                ],
                "adjustments": [
                    {
                        "id": str(item.adjustment_id),
                        "type": item.adjustment_type,
                        "label": item.adjustment_label,
                        "date": item.transaction_date.isoformat(),
                        "reference": item.reference,
                        "reason": item.reason,
                        "effect": item.effect,
                        "amount": str(item.amount),
                    }
                    for item in adjustments
                ],
            }
        )
    return {
        "run_id": str(run.pk),
        "period_start": run.period_start.isoformat(),
        "period_end": run.period_end.isoformat(),
        "attendance_period_id": str(run.attendance_period_id) if run.attendance_period_id else None,
        "attendance_revision": run.attendance_revision,
        "revision": run.revision,
        "calculation_version": run.calculation_version,
        "employee_count": run.employee_count,
        "totals": {
            "basic": str(run.total_basic),
            "allowances": str(run.total_allowances),
            "overtime": str(run.total_overtime),
            "other_earnings": str(run.total_other_earnings),
            "gross": str(run.total_gross),
            "advance_recovery": str(run.total_advance_recovery),
            "other_deductions": str(run.total_other_deductions),
            "deductions": str(run.total_deductions),
            "net": str(run.total_net),
        },
        "rows": payload_rows,
    }


def _clear_run_snapshot_locked(*, run: PayrollRun) -> None:
    line_ids = list(PayrollRunLine.objects.for_company(run.company).filter(run=run).values_list("pk", flat=True))
    if line_ids:
        PayrollRunLineAdjustment.objects.for_company(run.company).filter(run_line_id__in=line_ids).delete()
        PayrollRunLineComponent.objects.for_company(run.company).filter(run_line_id__in=line_ids).delete()
        PayrollRunLine.objects.for_company(run.company).filter(pk__in=line_ids).delete()


def _run_totals(rows: list[dict[str, Any]]) -> dict[str, Decimal | int]:
    keys = ["basic", "allowances", "overtime_amount", "other_earnings", "gross", "advance_recovery", "other_deductions", "total_deductions", "net"]
    totals: dict[str, Decimal | int] = {key: Decimal("0") for key in keys}
    totals["employee_count"] = len(rows)
    for row in rows:
        for key in keys:
            totals[key] = Decimal(totals[key]) + Decimal(row[key])
    return totals


@transaction.atomic
def calculate_payroll_run(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    request: HttpRequest | None = None,
) -> PayrollRun:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    start, end = month_bounds(period_start)
    run = PayrollRun.objects.select_for_update().for_company(company).filter(period_start=start).first()
    if run and run.status not in {PayrollRunStatus.DRAFT, PayrollRunStatus.CALCULATED}:
        raise ValidationError({"payroll": f"A payroll run in {run.get_status_display()} cannot be recalculated."})

    calculation = _build_calculation_locked(company=company, period_start=start)
    if calculation["blockers"]:
        first = calculation["blockers"][:20]
        suffix = "" if len(calculation["blockers"]) <= 20 else f" (+{len(calculation['blockers']) - 20} more)"
        raise ValidationError({"payroll": "Calculation blocked: " + " | ".join(first) + suffix})

    if run is None:
        run = PayrollRun(company=company, period_start=start, period_end=end)
    before = {
        "status": run.status,
        "revision": run.revision,
        "net": str(run.total_net),
        "source_fingerprint": run.source_fingerprint,
    }
    if not run._state.adding:
        _clear_run_snapshot_locked(run=run)

    run.attendance_period = calculation["attendance"]
    run.attendance_revision = calculation["attendance"].revision
    run.status = PayrollRunStatus.CALCULATED
    run.revision += 1
    run.calculation_version = 1
    run.source_fingerprint = calculation["source_fingerprint"]
    run.snapshot_fingerprint = ""
    run.calculated_at = timezone.now()
    run.calculated_by = actor_membership.user
    run.submitted_at = None
    run.submitted_by = None
    run.approved_at = None
    run.approved_by = None
    run.reviewer_note = ""
    totals = _run_totals(calculation["rows"])
    run.employee_count = totals["employee_count"]  # type: ignore[assignment]
    run.total_basic = _money(totals["basic"])  # type: ignore[arg-type]
    run.total_allowances = _money(totals["allowances"])  # type: ignore[arg-type]
    run.total_overtime = _money(totals["overtime_amount"])  # type: ignore[arg-type]
    run.total_other_earnings = _money(totals["other_earnings"])  # type: ignore[arg-type]
    run.total_gross = _money(totals["gross"])  # type: ignore[arg-type]
    run.total_advance_recovery = _money(totals["advance_recovery"])  # type: ignore[arg-type]
    run.total_other_deductions = _money(totals["other_deductions"])  # type: ignore[arg-type]
    run.total_deductions = _money(totals["total_deductions"])  # type: ignore[arg-type]
    run.total_net = _money(totals["net"])  # type: ignore[arg-type]
    run.full_clean()
    run.save()

    for item in calculation["rows"]:
        employee: InternalEmployee = item["employee"]
        organization: EmployeeOrganizationAssignment | None = item["organization"]
        overtime: AttendanceOvertimeEntry | None = item["overtime"]
        line = PayrollRunLine(
            company=company,
            run=run,
            employee=employee,
            employee_number=employee.employee_number,
            employee_name=employee.full_name,
            branch_id_snapshot=organization.branch_id if organization else None,
            branch_code=organization.branch.code if organization else "",
            branch_name=organization.branch.name if organization else "",
            department_id_snapshot=organization.department_id if organization else None,
            department_code=organization.department.code if organization else "",
            department_name=organization.department.name if organization else "",
            position=organization.position if organization else "",
            regular_hours=item["regular_hours"],
            absent_days=item["absent_days"],
            leave_days=item["leave_days"],
            sick_days=item["sick_days"],
            holiday_days=item["holiday_days"],
            off_days=item["off_days"],
            overtime_hours=item["overtime_hours"],
            overtime_amount=item["overtime_amount"],
            overtime_policy_code=overtime.policy_code if overtime else "",
            overtime_policy_name=overtime.policy_name if overtime else "",
            overtime_rate=overtime.overtime_rate if overtime else None,
            basic=item["basic"],
            allowances=item["allowances"],
            other_earnings=item["other_earnings"],
            gross=item["gross"],
            advance_recovery=item["advance_recovery"],
            other_deductions=item["other_deductions"],
            total_deductions=item["total_deductions"],
            net=item["net"],
        )
        line.full_clean()
        line.save()
        for contribution in item["components"]:
            source_line: SalaryStructureLine = contribution["line"]
            component = PayrollRunLineComponent(
                company=company,
                run_line=line,
                salary_structure=contribution["structure"],
                salary_structure_line=source_line,
                component_code=source_line.component_code,
                component_name=source_line.component_name,
                component_category=source_line.component_category,
                component_recurrence=source_line.component_recurrence,
                component_calculation=source_line.component_calculation,
                wps_mapping=source_line.wps_mapping,
                base_amount=source_line.amount,
                effective_from=contribution["effective_from"],
                effective_to=contribution["effective_to"],
                proration_days=contribution["proration_days"],
                proration_denominator=contribution["proration_denominator"],
                amount=contribution["amount"],
            )
            component.full_clean()
            component.save()
        for adjustment_item in item["adjustments"]:
            adjustment: PayrollAdjustment = adjustment_item["adjustment"]
            snapshot = PayrollRunLineAdjustment(
                company=company,
                run_line=line,
                adjustment=adjustment,
                adjustment_type=adjustment.adjustment_type,
                adjustment_label=adjustment.get_adjustment_type_display(),
                transaction_date=adjustment.transaction_date,
                reference=adjustment.reference,
                reason=adjustment.reason,
                amount=adjustment.amount,
                effect=adjustment_item["effect"],
            )
            snapshot.full_clean()
            snapshot.save()

    run.snapshot_fingerprint = _hash_payload(_snapshot_payload_locked(run=run))
    run.save(update_fields=("snapshot_fingerprint", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.payroll_run.calculated" if before["revision"] == 0 else "internal.payroll_run.recalculated",
        object_type="internal_payroll.PayrollRun",
        object_id=run.pk,
        object_label=str(run),
        actor_membership=actor_membership,
        before=before,
        after={
            "status": run.status,
            "revision": run.revision,
            "employee_count": run.employee_count,
            "gross": str(run.total_gross),
            "deductions": str(run.total_deductions),
            "net": str(run.total_net),
            "attendance_revision": run.attendance_revision,
            "source_fingerprint": run.source_fingerprint,
            "snapshot_fingerprint": run.snapshot_fingerprint,
        },
        request=request,
    )
    return run


def _verify_snapshot_locked(*, run: PayrollRun) -> None:
    if not run.snapshot_fingerprint:
        raise ValidationError({"payroll": "Payroll calculation snapshot is incomplete."})
    actual_snapshot = _hash_payload(_snapshot_payload_locked(run=run))
    if actual_snapshot != run.snapshot_fingerprint:
        raise ValidationError({"payroll": "Payroll snapshot integrity check failed."})


def _verify_run_locked(*, run: PayrollRun, require_locked_attendance: bool = True) -> None:
    if not run.source_fingerprint or not run.snapshot_fingerprint:
        raise ValidationError({"payroll": "Payroll calculation snapshot is incomplete. Recalculate the run."})
    calculation = _build_calculation_locked(company=run.company, period_start=run.period_start)
    if calculation["blockers"]:
        raise ValidationError({"payroll": "Payroll inputs are no longer valid. Recalculate after resolving the input issues."})
    if require_locked_attendance and calculation["attendance"].status != AttendancePeriodStatus.LOCKED:
        raise ValidationError({"attendance": "Attendance must be Locked before payroll can enter Finance Review."})
    if calculation["source_fingerprint"] != run.source_fingerprint:
        raise ValidationError({"payroll": "Payroll source data changed after calculation. Recalculate before continuing."})
    try:
        _verify_snapshot_locked(run=run)
    except ValidationError as exc:
        raise ValidationError({"payroll": "Payroll snapshot integrity check failed. Recalculate before continuing."}) from exc


@transaction.atomic
def verify_payroll_run_integrity(
    *, company, period_start: date, verify_source: bool = True, require_locked_attendance: bool = False
) -> PayrollRun:
    """Verify a saved payroll run without changing its lifecycle state.

    The payment service can call this with ``verify_source=False`` for an already-approved historical snapshot;
    Calculated/Review UI validation uses source verification to detect stale inputs before an action.
    """

    start, _end = month_bounds(period_start)
    run = PayrollRun.objects.select_for_update().for_company(company).filter(period_start=start).first()
    if run is None or run.status == PayrollRunStatus.DRAFT:
        raise ValidationError({"payroll": "No calculated payroll snapshot exists for this period."})
    if verify_source:
        _verify_run_locked(run=run, require_locked_attendance=require_locked_attendance)
    else:
        _verify_snapshot_locked(run=run)
    return run


@transaction.atomic
def reset_payroll_run(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    reason: str = "",
    request: HttpRequest | None = None,
) -> PayrollRun:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    start, end = month_bounds(period_start)
    run = PayrollRun.objects.select_for_update().for_company(company).filter(period_start=start).first()
    if run is None:
        raise ValidationError({"payroll": "No calculated payroll run exists for this period."})
    if run.status != PayrollRunStatus.CALCULATED:
        raise ValidationError({"payroll": "Only a Calculated payroll run can be reset to Draft."})
    before = {"status": run.status, "revision": run.revision, "net": str(run.total_net)}
    _clear_run_snapshot_locked(run=run)
    run.status = PayrollRunStatus.DRAFT
    run.attendance_period = None
    run.attendance_revision = 0
    run.source_fingerprint = ""
    run.snapshot_fingerprint = ""
    run.employee_count = 0
    for field in (
        "total_basic", "total_allowances", "total_overtime", "total_other_earnings", "total_gross",
        "total_advance_recovery", "total_other_deductions", "total_deductions", "total_net",
    ):
        setattr(run, field, Decimal("0"))
    run.calculated_at = None
    run.calculated_by = None
    run.submitted_at = None
    run.submitted_by = None
    run.approved_at = None
    run.approved_by = None
    run.reviewer_note = ""
    run.full_clean()
    run.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.payroll_run.reset_to_draft",
        object_type="internal_payroll.PayrollRun",
        object_id=run.pk,
        object_label=str(run),
        actor_membership=actor_membership,
        before=before,
        after={"status": run.status, "revision": run.revision},
        metadata={"reason": reason.strip()} if reason.strip() else {},
        request=request,
    )
    return run


@transaction.atomic
def transition_payroll_run(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    action: str,
    note: str = "",
    confirmed: bool = False,
    request: HttpRequest | None = None,
) -> PayrollRun:
    company = actor_membership.company
    start, _end = month_bounds(period_start)
    normalized = action.strip().lower().replace("-", "_")
    if normalized == "submit_review":
        _require_internal_edit(actor_membership)
    else:
        _require_internal_approval(actor_membership)
    run = (
        # attendance_period is nullable; scope the row lock to PayrollRun so
        # PostgreSQL does not attempt FOR UPDATE on the nullable outer-joined
        # attendance row.
        PayrollRun.objects.select_for_update(of=("self",)).for_company(company)
        .filter(period_start=start)
        .select_related("attendance_period")
        .first()
    )
    if run is None:
        raise ValidationError({"payroll": "Calculate payroll before changing its workflow status."})
    before = {"status": run.status, "reviewer_note": run.reviewer_note}
    now = timezone.now()

    if normalized == "submit_review":
        if run.status != PayrollRunStatus.CALCULATED:
            raise ValidationError({"payroll": "Only a Calculated payroll run can be submitted to Finance Review."})
        _verify_run_locked(run=run, require_locked_attendance=True)
        run.status = PayrollRunStatus.REVIEW
        run.submitted_at = now
        run.submitted_by = actor_membership.user
        audit_action = "internal.payroll_run.submitted_for_review"
    elif normalized == "return_for_changes":
        if run.status != PayrollRunStatus.REVIEW:
            raise ValidationError({"payroll": "Only a payroll run in Review can be returned for changes."})
        note = note.strip()
        if not note:
            raise ValidationError({"note": "A reviewer correction note is required."})
        run.status = PayrollRunStatus.CALCULATED
        run.submitted_at = None
        run.submitted_by = None
        run.reviewer_note = note
        audit_action = "internal.payroll_run.returned_for_changes"
    elif normalized == "approve":
        if run.status != PayrollRunStatus.REVIEW:
            raise ValidationError({"payroll": "Only a payroll run in Finance Review can be approved."})
        if not confirmed:
            raise ValidationError({"confirmation": "Reviewer confirmation is required before approval."})
        _verify_run_locked(run=run, require_locked_attendance=True)
        run.status = PayrollRunStatus.APPROVED
        run.approved_at = now
        run.approved_by = actor_membership.user
        run.reviewer_note = note.strip()
        audit_action = "internal.payroll_run.approved"
    else:
        raise ValidationError({"action": "Unsupported payroll workflow action."})

    run.full_clean()
    run.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action=audit_action,
        object_type="internal_payroll.PayrollRun",
        object_id=run.pk,
        object_label=str(run),
        actor_membership=actor_membership,
        before=before,
        after={
            "status": run.status,
            "submitted_at": run.submitted_at.isoformat() if run.submitted_at else None,
            "approved_at": run.approved_at.isoformat() if run.approved_at else None,
            "reviewer_note": run.reviewer_note,
            "revision": run.revision,
        },
        metadata={"note": note.strip()} if note.strip() else {},
        request=request,
    )
    return run

@transaction.atomic
def preview_payroll_run(*, company, period_start: date) -> dict[str, Any]:
    """Build the authoritative payroll preflight without persisting a financial snapshot."""

    calculation = _build_calculation_locked(company=company, period_start=period_start)
    rows: list[dict[str, Any]] = []
    for item in calculation["rows"]:
        employee: InternalEmployee = item["employee"]
        organization: EmployeeOrganizationAssignment | None = item["organization"]
        overtime: AttendanceOvertimeEntry | None = item["overtime"]
        rows.append(
            {
                "employeeId": str(employee.pk),
                "employeeCode": employee.employee_number,
                "name": employee.full_name,
                "position": organization.position if organization else "",
                "department": organization.department.name if organization else "",
                "branchId": str(organization.branch_id) if organization else None,
                "branch": organization.branch.name if organization else "",
                "basic": str(item["basic"]),
                "allowances": str(item["allowances"]),
                "overtime": str(item["overtime_amount"]),
                "otHours": str(item["overtime_hours"]),
                "otPolicy": overtime.policy_name if overtime else "",
                "otherEarnings": str(item["other_earnings"]),
                "gross": str(item["gross"]),
                "advances": str(item["advance_recovery"]),
                "deductions": str(item["other_deductions"]),
                "net": str(item["net"]),
                "blockers": list(item["blockers"]),
                "warnings": [],
                "readiness": "Blocked" if item["blockers"] else "Ready",
                "salaryComponents": [
                    {
                        "code": contribution["line"].component_code,
                        "name": contribution["line"].component_name,
                        "type": contribution["line"].component_category,
                        "wpsMap": contribution["line"].get_wps_mapping_display(),
                        "baseAmount": str(contribution["line"].amount),
                        "amount": str(contribution["amount"]),
                        "effectiveFrom": contribution["effective_from"].isoformat(),
                        "effectiveTo": contribution["effective_to"].isoformat(),
                        "prorationDays": contribution["proration_days"],
                        "prorationDenominator": contribution["proration_denominator"],
                    }
                    for contribution in item["components"]
                ],
                "adjustmentLines": [
                    {
                        "id": str(adjustment_item["adjustment"].pk),
                        "type": adjustment_item["adjustment"].get_adjustment_type_display(),
                        "amount": str(adjustment_item["adjustment"].amount),
                        "kind": adjustment_item["effect"],
                        "status": adjustment_item["adjustment"].get_status_display(),
                        "reason": adjustment_item["adjustment"].reason,
                    }
                    for adjustment_item in item["adjustments"]
                ],
                "attendance": {
                    "regularHours": str(item["regular_hours"]),
                    "absentDays": item["absent_days"],
                    "leaveDays": item["leave_days"],
                    "sickDays": item["sick_days"],
                    "holidayDays": item["holiday_days"],
                    "offDays": item["off_days"],
                },
            }
        )
    return {
        "rows": rows,
        "blockers": list(calculation["blockers"]),
        "attendance": calculation["attendance"],
        "proration_method": calculation["proration_method"],
    }
