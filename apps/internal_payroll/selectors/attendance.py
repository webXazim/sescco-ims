from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.core.models import Company
from apps.internal_payroll.models import (
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    AttendancePeriodStatus,
    EmployeeOrganizationAssignment,
    EmploymentStatus,
    InternalEmployee,
    SalaryStructure,
    SalaryStructureLine,
)
from apps.internal_payroll.services.attendance import month_bounds, operational_internal_employees


def attendance_period_for_company(*, company: Company, period_start: date) -> AttendancePeriod | None:
    start, _end = month_bounds(period_start)
    return (
        AttendancePeriod.objects.for_company(company)
        .select_related("submitted_by", "approved_by", "locked_by")
        .filter(period_start=start)
        .first()
    )


def _employee_assignment_as_of(employee: InternalEmployee, as_of: date) -> EmployeeOrganizationAssignment | None:
    history = getattr(employee, "attendance_org_history", None)
    if history is None:
        history = list(
            employee.organization_assignments.select_related("branch", "department")
            .filter(effective_from__lte=as_of)
            .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
            .order_by("-effective_from", "-created_at")
        )
    return next(
        (
            item
            for item in history
            if item.effective_from <= as_of and (item.effective_to is None or item.effective_to >= as_of)
        ),
        None,
    )


def attendance_roster_for_company(*, company: Company, period_start: date) -> list[InternalEmployee]:
    start, end = month_bounds(period_start)
    assignments = (
        EmployeeOrganizationAssignment.objects.for_company(company)
        .select_related("branch", "department")
        .filter(effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
        .order_by("-effective_from", "-created_at")
    )
    return list(
        operational_internal_employees(company=company)
        .filter(joining_date__lte=end)
        .filter(Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=start))
        .exclude(status=EmploymentStatus.INACTIVE)
        .prefetch_related(Prefetch("organization_assignments", queryset=assignments, to_attr="attendance_org_history"))
        .order_by("employee_number", "full_name")
    )


def _display_attendance_value(entry: AttendanceEntry) -> str:
    if entry.code:
        return entry.code
    hours = entry.regular_hours
    return format(hours.normalize(), "f") if hours != hours.to_integral() else str(int(hours))


def _period_label(start: date) -> str:
    return f"{month_name[start.month]} {start.year}"


def _user_label(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name().strip() or user.username


def serialize_attendance_period(period: AttendancePeriod | None, *, period_start: date, membership=None) -> dict[str, object]:
    start, end = month_bounds(period_start)
    status = period.status if period else AttendancePeriodStatus.DRAFT
    can_edit = bool(membership and membership_can_edit(membership, Workspace.INTERNAL) and status == AttendancePeriodStatus.DRAFT)
    can_approve = bool(membership and membership_can_workspace(membership, Workspace.INTERNAL) and membership_has_capability(membership, Capability.APPROVE))
    if status == AttendancePeriodStatus.DRAFT:
        next_action = "submit" if can_edit else None
    elif status == AttendancePeriodStatus.SUBMITTED:
        next_action = "approve" if can_approve else None
    elif status == AttendancePeriodStatus.APPROVED:
        next_action = "lock" if can_approve else None
    else:
        next_action = None
    return {
        "id": str(period.pk) if period else None,
        "exists": period is not None,
        "period": f"{start:%Y-%m}",
        "label": _period_label(start),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "status": AttendancePeriodStatus(status).label,
        "statusValue": status,
        "revision": period.revision if period else 0,
        "canEdit": can_edit,
        "canApprove": can_approve,
        "nextAction": next_action,
        "submittedAt": period.submitted_at.isoformat() if period and period.submitted_at else None,
        "submittedBy": _user_label(period.submitted_by) if period else None,
        "approvedAt": period.approved_at.isoformat() if period and period.approved_at else None,
        "approvedBy": _user_label(period.approved_by) if period else None,
        "lockedAt": period.locked_at.isoformat() if period and period.locked_at else None,
        "lockedBy": _user_label(period.locked_by) if period else None,
    }


def _salary_structure_as_of(*, company: Company, employee: InternalEmployee, as_of: date) -> SalaryStructure | None:
    lines = SalaryStructureLine.objects.for_company(company).order_by("component_category", "component_code")
    return (
        SalaryStructure.objects.for_company(company)
        .filter(employee=employee, effective_from__lte=as_of)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
        .prefetch_related(Prefetch("lines", queryset=lines, to_attr="attendance_salary_lines"))
        .order_by("-effective_from")
        .first()
    )


def _overtime_setup_for_employee(*, company: Company, employee: InternalEmployee, as_of: date) -> dict[str, object]:
    structure = _salary_structure_as_of(company=company, employee=employee, as_of=as_of)
    if structure is None:
        return {"configured": False, "reason": "No salary structure is effective at period end."}
    if not structure.overtime_policy_name or structure.overtime_divisor is None or structure.overtime_multiplier is None:
        return {"configured": False, "reason": "No overtime policy is assigned to the effective salary structure."}
    lines = getattr(structure, "attendance_salary_lines", [])
    base_line = next((item for item in lines if item.component_code == structure.overtime_base_component_code), None)
    if base_line is None:
        return {"configured": False, "reason": "The overtime base component is missing from the salary structure."}
    divisor = Decimal(structure.overtime_divisor)
    multiplier = Decimal(structure.overtime_multiplier)
    overtime_rate = (base_line.amount / divisor * multiplier).quantize(Decimal("0.0001"))
    return {
        "configured": True,
        "salaryStructureId": str(structure.pk),
        "policyCode": structure.overtime_policy_code,
        "policyName": structure.overtime_policy_name,
        "baseComponent": structure.overtime_base_component_name,
        "baseAmount": str(base_line.amount),
        "divisor": str(divisor),
        "multiplier": str(multiplier),
        "rate": str(overtime_rate),
    }


def attendance_period_context(*, company: Company, period_start: date, membership=None) -> dict[str, object]:
    start, end = month_bounds(period_start)
    period = attendance_period_for_company(company=company, period_start=start)
    roster = attendance_roster_for_company(company=company, period_start=start)

    entries: list[AttendanceEntry] = []
    overtime_rows: list[AttendanceOvertimeEntry] = []
    if period is not None:
        entries = list(
            AttendanceEntry.objects.for_company(company)
            .filter(period=period)
            .select_related("employee")
            .order_by("employee__employee_number", "work_date")
        )
        overtime_rows = list(
            AttendanceOvertimeEntry.objects.for_company(company)
            .filter(period=period)
            .select_related("employee", "salary_structure")
            .order_by("employee__employee_number")
        )

    records: dict[str, dict[str, str]] = {}
    for entry in entries:
        records.setdefault(str(entry.employee_id), {})[str(entry.work_date.day)] = _display_attendance_value(entry)

    overtime_by_employee = {str(item.employee_id): item for item in overtime_rows}
    roster_payload: list[dict[str, object]] = []
    overtime_payload: dict[str, dict[str, object]] = {}
    missing_count = 0
    for employee in roster:
        assignment = _employee_assignment_as_of(employee, end)
        employee_key = str(employee.pk)
        employee_record = records.get(employee_key, {})
        employed_from = max(employee.joining_date, start)
        employed_to = min(employee.employment_end_date or end, end)
        required_days = (employed_to - employed_from).days + 1
        missing_count += max(0, required_days - len(employee_record))
        roster_payload.append(
            {
                "id": employee_key,
                "employeeId": employee.employee_number,
                "name": employee.full_name,
                "position": assignment.position if assignment else "",
                "branchId": str(assignment.branch_id) if assignment else None,
                "branch": assignment.branch.name if assignment else "",
                "departmentId": str(assignment.department_id) if assignment else None,
                "department": assignment.department.name if assignment else "",
                "joining": employee.joining_date.isoformat(),
                "employmentEnd": employee.employment_end_date.isoformat() if employee.employment_end_date else None,
                "status": employee.get_status_display(),
            }
        )
        setup = _overtime_setup_for_employee(company=company, employee=employee, as_of=end)
        saved = overtime_by_employee.get(employee_key)
        overtime_payload[employee_key] = {
            **setup,
            "hours": str(saved.hours) if saved else "0.00",
            "amount": str(saved.amount) if saved else "0.00",
            "saved": saved is not None,
        }
        if saved:
            overtime_payload[employee_key].update(
                {
                    "salaryStructureId": str(saved.salary_structure_id),
                    "policyCode": saved.policy_code,
                    "policyName": saved.policy_name,
                    "baseComponent": saved.base_component_name,
                    "baseAmount": str(saved.base_amount),
                    "divisor": str(saved.divisor),
                    "multiplier": str(saved.multiplier),
                    "rate": str(saved.overtime_rate),
                }
            )

    return {
        "period": serialize_attendance_period(period, period_start=start, membership=membership),
        "roster": roster_payload,
        "records": records,
        "overtime": overtime_payload,
        "summary": {
            "employeeCount": len(roster_payload),
            "entryCount": len(entries),
            "missingCount": missing_count,
            "overtimeEmployees": len(overtime_rows),
            "overtimeHours": str(sum((item.hours for item in overtime_rows), Decimal("0"))),
            "overtimeAmount": str(sum((item.amount for item in overtime_rows), Decimal("0"))),
        },
    }
