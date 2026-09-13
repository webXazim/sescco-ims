from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q

from apps.core.models import AuditArea, AuditEvent, Company
from apps.internal_payroll.models import (
    AttendanceCode,
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    EmployeePaymentProfile,
    InternalEmployee,
    PayrollAdjustment,
    PayrollRunLine,
    SalaryPaymentRow,
    SalaryStructure,
)


def _period_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _money(value: Decimal | int | str | None) -> str:
    return str(value if value is not None else Decimal("0"))


def _attendance_profile(*, company: Company, employee: InternalEmployee, period_start: date) -> dict[str, object]:
    period = (
        AttendancePeriod.objects.for_company(company)
        .filter(period_start=period_start)
        .first()
    )
    if period is None:
        return {
            "period": f"{period_start:%Y-%m}",
            "label": _period_label(period_start),
            "status": "Not created",
            "statusValue": None,
            "present": 0,
            "absent": 0,
            "leave": 0,
            "sick": 0,
            "holiday": 0,
            "off": 0,
            "regularHours": "0.00",
            "otHours": "0.00",
            "otAmount": "0.00",
            "available": False,
        }

    entries = list(
        AttendanceEntry.objects.for_company(company)
        .filter(period=period, employee=employee)
        .order_by("work_date")
    )
    overtime = (
        AttendanceOvertimeEntry.objects.for_company(company)
        .filter(period=period, employee=employee)
        .first()
    )

    regular_hours = sum((item.regular_hours for item in entries), Decimal("0"))
    present = sum(1 for item in entries if item.regular_hours > 0)
    absent = sum(1 for item in entries if item.code == AttendanceCode.ABSENT)
    leave = sum(1 for item in entries if item.code == AttendanceCode.LEAVE)
    sick = sum(1 for item in entries if item.code == AttendanceCode.SICK)
    holiday = sum(1 for item in entries if item.code == AttendanceCode.HOLIDAY)
    off = sum(1 for item in entries if item.code == AttendanceCode.OFF)

    return {
        "period": f"{period.period_start:%Y-%m}",
        "label": _period_label(period.period_start),
        "status": period.get_status_display(),
        "statusValue": period.status,
        "present": present,
        "absent": absent,
        "leave": leave,
        "sick": sick,
        "holiday": holiday,
        "off": off,
        "regularHours": _money(regular_hours),
        "otHours": _money(overtime.hours if overtime else Decimal("0")),
        "otAmount": _money(overtime.amount if overtime else Decimal("0")),
        "available": bool(entries or overtime),
    }


def _payroll_history(*, company: Company, employee: InternalEmployee) -> list[dict[str, object]]:
    payment_rows = (
        SalaryPaymentRow.objects.for_company(company)
        .select_related("batch")
        .order_by("-claim_active", "-created_at")
    )
    lines = (
        PayrollRunLine.objects.for_company(company)
        .filter(employee=employee)
        .select_related("run")
        .prefetch_related(Prefetch("payment_rows", queryset=payment_rows, to_attr="profile_payment_rows"))
        .order_by("-run__period_start", "-created_at")
    )

    history: list[dict[str, object]] = []
    for line in lines:
        payment_candidates = list(getattr(line, "profile_payment_rows", []))
        payment = next((item for item in payment_candidates if item.claim_active), payment_candidates[0] if payment_candidates else None)
        extras = line.allowances + line.overtime_amount + line.other_earnings
        reference = payment.batch.reference if payment is not None else f"Payroll revision {line.run.revision}"
        history.append(
            {
                "lineId": str(line.pk),
                "runId": str(line.run_id),
                "period": _period_label(line.run.period_start),
                "periodKey": f"{line.run.period_start:%Y-%m}",
                "reference": reference,
                "basic": _money(line.basic),
                "allowances": _money(line.allowances),
                "overtime": _money(line.overtime_amount),
                "otHours": _money(line.overtime_hours),
                "otherEarnings": _money(line.other_earnings),
                "extras": _money(extras),
                "gross": _money(line.gross),
                "deductions": _money(line.total_deductions),
                "net": _money(line.net),
                "payment": payment.get_status_display() if payment is not None else "Not prepared",
                "paymentStatusValue": payment.status if payment is not None else None,
                "paymentReference": payment.transaction_reference if payment is not None else "",
                "status": line.run.get_status_display(),
                "statusValue": line.run.status,
            }
        )
    return history


_ACTIVITY_LABELS = {
    "internal.employee.created": "Employee created",
    "internal.employee.updated": "Employee details updated",
    "internal.employee.organization_changed": "Organization assignment changed",
    "internal.employee.lifecycle.active": "Employee activated",
    "internal.employee.lifecycle.on_leave": "Employee placed on leave",
    "internal.employee.lifecycle.inactive": "Employee activity stopped",
    "internal.employee.lifecycle.terminated": "Employment terminated",
    "internal.employee.archived": "Employee archived",
    "internal.employee.archive_restored": "Employee restored from archive",
    "internal.employee.moved_to_trash": "Employee deleted to recovery",
    "internal.employee.trash_restored": "Employee restored from recovery",
    "internal.salary_structure.assigned": "Salary structure assigned",
    "internal.salary_structure.closed": "Salary structure period closed",
    "internal.employee_payment_profile.created": "Salary payment profile created",
    "internal.employee_payment_profile.updated": "Salary payment profile updated",
    "internal.employee_payment_profile.deleted_unused": "Unused salary payment profile deleted",
    "internal.salary_payment_batch.prepared": "Salary payment batch prepared",
    "internal.salary_payment_batch.exported": "Salary payment file exported",
    "internal.salary_payment_batch.processing_started": "Salary payment processing started",
    "internal.salary_payment_results.imported": "Salary payment results imported",
    "internal.salary_payment_row.retried": "Salary payment retried",
    "internal.salary_payment_batch.cancelled": "Salary payment batch cancelled",
    "internal.salary_payment_batch.closed": "Salary payment batch closed",
    "internal.salary_payment_batch.reopened": "Salary payment batch reopened",
    "internal.payroll_adjustment.created": "Payroll adjustment created",
    "internal.payroll_adjustment.updated": "Payroll adjustment updated",
    "internal.payroll_adjustment.submitted": "Payroll adjustment submitted",
    "internal.payroll_adjustment.approved": "Payroll adjustment approved",
    "internal.payroll_adjustment.returned_to_draft": "Payroll adjustment returned to draft",
    "internal.payroll_run.calculated": "Payroll calculated",
    "internal.payroll_run.recalculated": "Payroll recalculated",
    "internal.payroll_run.submitted_for_review": "Payroll submitted for review",
    "internal.payroll_run.returned_for_changes": "Payroll returned for changes",
    "internal.payroll_run.approved": "Payroll approved",
    "internal.payroll_run.reset_to_draft": "Payroll reset to draft",
    "internal.attendance_entries.saved": "Attendance updated",
    "internal.attendance_overtime.saved": "Overtime updated",
    "internal.attendance_period.submitted": "Attendance submitted for review",
    "internal.attendance_period.approved": "Attendance approved",
    "internal.attendance_period.locked": "Attendance locked",
}


def _activity_title(action: str) -> str:
    if action in _ACTIVITY_LABELS:
        return _ACTIVITY_LABELS[action]
    tail = action.split(".")[-1].replace("_", " ").strip()
    return tail[:1].upper() + tail[1:] if tail else action


def _attendance_event_mentions_employee(event: AuditEvent, employee_number: str) -> bool:
    if event.action not in {"internal.attendance_entries.saved", "internal.attendance_overtime.saved"}:
        return True
    payloads: list[object] = []
    for container in (event.before, event.after):
        if isinstance(container, dict):
            payloads.extend(container.get("entries", []) if isinstance(container.get("entries"), list) else [])
            payloads.extend(container.get("overtime", []) if isinstance(container.get("overtime"), list) else [])
    return any(isinstance(item, dict) and str(item.get("employee") or "") == employee_number for item in payloads)


def _employee_activity(*, company: Company, employee: InternalEmployee, limit: int = 12) -> list[dict[str, object]]:
    adjustment_ids = [str(value) for value in PayrollAdjustment.objects.for_company(company).filter(employee=employee).values_list("pk", flat=True)]
    structure_ids = [str(value) for value in SalaryStructure.objects.for_company(company).filter(employee=employee).values_list("pk", flat=True)]
    run_ids = [str(value) for value in PayrollRunLine.objects.for_company(company).filter(employee=employee).values_list("run_id", flat=True).distinct()]
    attendance_period_ids = {
        str(value)
        for value in AttendanceEntry.objects.for_company(company).filter(employee=employee).values_list("period_id", flat=True).distinct()
    }
    attendance_period_ids.update(
        str(value)
        for value in AttendanceOvertimeEntry.objects.for_company(company).filter(employee=employee).values_list("period_id", flat=True).distinct()
    )
    payment_profile = EmployeePaymentProfile.objects.for_company(company).filter(employee=employee).first()
    employee_payment_rows = SalaryPaymentRow.objects.for_company(company).filter(employee=employee)
    payment_row_ids = [str(value) for value in employee_payment_rows.values_list("pk", flat=True)]
    payment_batch_ids = [str(value) for value in employee_payment_rows.values_list("batch_id", flat=True).distinct()]

    related = Q(object_type="internal_payroll.InternalEmployee", object_id=str(employee.pk))
    if adjustment_ids:
        related |= Q(object_type="internal_payroll.PayrollAdjustment", object_id__in=adjustment_ids)
    if structure_ids:
        related |= Q(object_type="internal_payroll.SalaryStructure", object_id__in=structure_ids)
    if run_ids:
        related |= Q(object_type="internal_payroll.PayrollRun", object_id__in=run_ids)
    if attendance_period_ids:
        related |= Q(object_type="internal_payroll.AttendancePeriod", object_id__in=list(attendance_period_ids))
    if payment_profile is not None:
        related |= Q(object_type="internal_payroll.EmployeePaymentProfile", object_id=str(payment_profile.pk))
    if payment_row_ids:
        related |= Q(object_type="internal_payroll.SalaryPaymentRow", object_id__in=payment_row_ids)
    if payment_batch_ids:
        related |= Q(object_type="internal_payroll.SalaryPaymentBatch", object_id__in=payment_batch_ids)

    # Salary structure events also store the immutable employee number in metadata.
    related |= Q(metadata__employee_number=employee.employee_number)

    candidates = (
        AuditEvent.objects.filter(company=company, area=AuditArea.INTERNAL)
        .filter(related)
        .order_by("-created_at", "-id")[: max(limit * 4, 40)]
    )

    result: list[dict[str, object]] = []
    for event in candidates:
        if event.object_type == "internal_payroll.AttendancePeriod" and not _attendance_event_mentions_employee(event, employee.employee_number):
            continue
        actor = event.actor_display_name or event.actor_username or "System"
        note = ""
        if isinstance(event.metadata, dict):
            note = str(event.metadata.get("note") or event.metadata.get("reason") or "").strip()
        result.append(
            {
                "id": str(event.pk),
                "action": event.action,
                "title": _activity_title(event.action),
                "actor": actor,
                "at": event.created_at.isoformat(),
                "note": note,
                "objectLabel": event.object_label,
            }
        )
        if len(result) >= limit:
            break
    return result


def employee_profile_context(*, company: Company, employee: InternalEmployee, period_start: date) -> dict[str, object]:
    if employee.company_id != company.pk:
        raise ValueError("Employee does not belong to the active company.")
    organization_history = list(
        employee.organization_assignments.select_related("branch", "department").order_by("-effective_from", "-created_at")
    )
    return {
        "employeeId": str(employee.pk),
        "employeeNumber": employee.employee_number,
        "period": f"{period_start:%Y-%m}",
        "organizationHistory": [
            {
                "id": str(item.pk),
                "effective": item.effective_from.isoformat(),
                "effectiveTo": item.effective_to.isoformat() if item.effective_to else None,
                "branchId": str(item.branch_id), "branch": item.branch.name,
                "departmentId": str(item.department_id), "department": item.department.name,
                "position": item.position, "reason": item.reason, "createdAt": item.created_at.isoformat(),
            }
            for item in organization_history
        ],
        "attendance": _attendance_profile(company=company, employee=employee, period_start=period_start),
        "payrollHistory": _payroll_history(company=company, employee=employee),
        "activity": _employee_activity(company=company, employee=employee),
    }
