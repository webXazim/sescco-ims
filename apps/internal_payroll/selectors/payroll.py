from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.core.models import AuditArea, AuditEvent, Company
from apps.internal_payroll.models import (
    AttendancePeriodStatus,
    InternalPayrollPolicy,
    PayrollAdjustment,
    PayrollAdjustmentStatus,
    PayrollProrationMethod,
    PayrollRun,
    PayrollRunLine,
    PayrollRunLineAdjustment,
    PayrollRunLineComponent,
    PayrollRunStatus,
)
from apps.internal_payroll.services.attendance import month_bounds
from apps.internal_payroll.services.payroll import preview_payroll_run, verify_payroll_run_integrity


def _period_label(start: date) -> str:
    return f"{month_name[start.month]} {start.year}"


def _user_label(user) -> str | None:
    if user is None:
        return None
    return user.get_full_name().strip() or user.username


def serialize_payroll_policy(policy: InternalPayrollPolicy | None) -> dict[str, object]:
    method = policy.proration_method if policy else PayrollProrationMethod.NOT_CONFIGURED
    return {
        "id": str(policy.pk) if policy else None,
        "prorationMethod": method,
        "prorationLabel": PayrollProrationMethod(method).label,
        "configured": method != PayrollProrationMethod.NOT_CONFIGURED,
    }


def payroll_policy_for_company(*, company: Company) -> InternalPayrollPolicy | None:
    return InternalPayrollPolicy.objects.for_company(company).first()


def _adjustment_effect_label(adjustment: PayrollAdjustment) -> str:
    if adjustment.adjustment_type == "salary_advance":
        return "Advance balance"
    if adjustment.adjustment_type in {"bonus", "reimbursement", "other_earning"}:
        return "Adds to payable"
    if adjustment.adjustment_type == "advance_recovery":
        return "Advance recovery"
    return "Deducts from payable"


def serialize_payroll_adjustment(adjustment: PayrollAdjustment) -> dict[str, object]:
    return {
        "id": str(adjustment.pk),
        "employeeId": str(adjustment.employee_id),
        "date": adjustment.transaction_date.isoformat(),
        "period": _period_label(adjustment.period_start),
        "periodKey": f"{adjustment.period_start:%Y-%m}",
        "typeCode": adjustment.adjustment_type,
        "type": adjustment.get_adjustment_type_display(),
        "amount": str(adjustment.amount),
        "reason": adjustment.reason,
        "reference": adjustment.reference,
        "statusValue": adjustment.status,
        "status": adjustment.get_status_display(),
        "recoveryPlan": adjustment.recovery_plan,
        "installmentAmount": str(adjustment.installment_amount) if adjustment.installment_amount is not None else "",
        "recoveryStart": adjustment.recovery_start.isoformat() if adjustment.recovery_start else "",
        "submittedAt": adjustment.submitted_at.isoformat() if adjustment.submitted_at else None,
        "submittedBy": _user_label(adjustment.submitted_by),
        "approvedAt": adjustment.approved_at.isoformat() if adjustment.approved_at else None,
        "approvedBy": _user_label(adjustment.approved_by),
        "impact": _adjustment_effect_label(adjustment),
        "immutable": adjustment.status == PayrollAdjustmentStatus.APPROVED,
        "source": "Company database",
    }


def payroll_adjustments_for_period(*, company: Company, period_start: date) -> list[PayrollAdjustment]:
    start, _end = month_bounds(period_start)
    return list(
        PayrollAdjustment.objects.for_company(company)
        .filter(period_start=start)
        .select_related("employee", "submitted_by", "approved_by")
        .order_by("-transaction_date", "-created_at")
    )


def payroll_adjustments_by_employee(*, company: Company, period_start: date) -> dict[str, list[dict[str, object]]]:
    rows: dict[str, list[dict[str, object]]] = {}
    for item in payroll_adjustments_for_period(company=company, period_start=period_start):
        rows.setdefault(str(item.employee_id), []).append(serialize_payroll_adjustment(item))
    return rows


def _run_queryset(company: Company):
    components = PayrollRunLineComponent.objects.for_company(company).order_by("component_category", "component_code", "effective_from")
    adjustments = PayrollRunLineAdjustment.objects.for_company(company).order_by("transaction_date", "created_at")
    lines = (
        PayrollRunLine.objects.for_company(company)
        .select_related("employee")
        .prefetch_related(
            Prefetch("components", queryset=components, to_attr="payroll_components"),
            Prefetch("adjustments", queryset=adjustments, to_attr="payroll_adjustments"),
        )
        .order_by("employee_number", "employee_name")
    )
    return (
        PayrollRun.objects.for_company(company)
        .select_related("attendance_period", "calculated_by", "submitted_by", "approved_by")
        .prefetch_related(Prefetch("lines", queryset=lines, to_attr="payroll_lines"))
    )


def payroll_run_for_period(*, company: Company, period_start: date) -> PayrollRun | None:
    start, _end = month_bounds(period_start)
    return _run_queryset(company).filter(period_start=start).first()


def _serialize_snapshot_line(line: PayrollRunLine) -> dict[str, object]:
    components = getattr(line, "payroll_components", [])
    adjustments = getattr(line, "payroll_adjustments", [])
    return {
        "lineId": str(line.pk),
        "employeeId": str(line.employee_id),
        "employeeCode": line.employee_number,
        "name": line.employee_name,
        "position": line.position,
        "department": line.department_name,
        "branchId": str(line.branch_id_snapshot) if line.branch_id_snapshot else None,
        "branch": line.branch_name,
        "basic": str(line.basic),
        "allowances": str(line.allowances),
        "overtime": str(line.overtime_amount),
        "otHours": str(line.overtime_hours),
        "otPolicy": line.overtime_policy_name,
        "otherEarnings": str(line.other_earnings),
        "gross": str(line.gross),
        "advances": str(line.advance_recovery),
        "deductions": str(line.other_deductions),
        "net": str(line.net),
        "blockers": [],
        "warnings": [],
        "readiness": "Ready",
        "salaryComponents": [
            {
                "code": item.component_code,
                "name": item.component_name,
                "type": item.component_category,
                "wpsMap": item.get_wps_mapping_display(),
                "baseAmount": str(item.base_amount),
                "amount": str(item.amount),
                "effectiveFrom": item.effective_from.isoformat(),
                "effectiveTo": item.effective_to.isoformat(),
                "prorationDays": item.proration_days,
                "prorationDenominator": item.proration_denominator,
            }
            for item in components
        ],
        "adjustmentLines": [
            {
                "id": str(item.adjustment_id),
                "type": item.adjustment_label,
                "amount": str(item.amount),
                "kind": item.effect,
                "status": "Approved",
                "reason": item.reason,
            }
            for item in adjustments
        ],
        "pendingAdjustments": [],
        "attendance": {
            "regularHours": str(line.regular_hours),
            "absentDays": line.absent_days,
            "leaveDays": line.leave_days,
            "sickDays": line.sick_days,
            "holidayDays": line.holiday_days,
            "offDays": line.off_days,
        },
    }


def _audit_history(run: PayrollRun | None) -> list[dict[str, object]]:
    if run is None:
        return []
    rows = (
        AuditEvent.objects.filter(
            company=run.company,
            area=AuditArea.INTERNAL,
            object_type="internal_payroll.PayrollRun",
            object_id=str(run.pk),
        )
        .order_by("created_at")
    )
    labels = {
        "internal.payroll_run.calculated": "Payroll calculated",
        "internal.payroll_run.recalculated": "Payroll recalculated",
        "internal.payroll_run.reset_to_draft": "Reset to Draft",
        "internal.payroll_run.submitted_for_review": "Submitted for review",
        "internal.payroll_run.returned_for_changes": "Returned for changes",
        "internal.payroll_run.approved": "Payroll approved",
    }
    return [
        {
            "action": labels.get(item.action, item.action),
            "actor": item.actor_display_name or item.actor_username or "System",
            "at": item.created_at.isoformat(),
            "note": str(item.metadata.get("note") or item.metadata.get("reason") or ""),
        }
        for item in rows
    ]


def _run_payload(run: PayrollRun | None, *, period_start: date, membership=None) -> dict[str, object]:
    status = run.status if run else PayrollRunStatus.DRAFT
    can_edit = bool(membership and membership_can_edit(membership, Workspace.INTERNAL))
    can_approve = bool(
        membership
        and membership_can_workspace(membership, Workspace.INTERNAL)
        and membership_has_capability(membership, Capability.APPROVE)
    )
    return {
        "id": str(run.pk) if run else None,
        "exists": run is not None,
        "period": f"{period_start:%Y-%m}",
        "label": _period_label(period_start),
        "statusValue": status,
        "status": PayrollRunStatus(status).label,
        "revision": run.revision if run else 0,
        "calculationVersion": run.calculation_version if run else 1,
        "attendanceRevision": run.attendance_revision if run else 0,
        "calculatedAt": run.calculated_at.isoformat() if run and run.calculated_at else None,
        "calculatedBy": _user_label(run.calculated_by) if run else None,
        "submittedAt": run.submitted_at.isoformat() if run and run.submitted_at else None,
        "submittedBy": _user_label(run.submitted_by) if run else None,
        "approvedAt": run.approved_at.isoformat() if run and run.approved_at else None,
        "approvedBy": _user_label(run.approved_by) if run else None,
        "reviewerNote": run.reviewer_note if run else "",
        "canEdit": can_edit,
        "canApprove": can_approve,
        "totals": {
            "employeeCount": run.employee_count if run else 0,
            "basic": str(run.total_basic if run else Decimal("0")),
            "allowances": str(run.total_allowances if run else Decimal("0")),
            "overtime": str(run.total_overtime if run else Decimal("0")),
            "otherEarnings": str(run.total_other_earnings if run else Decimal("0")),
            "gross": str(run.total_gross if run else Decimal("0")),
            "advanceRecovery": str(run.total_advance_recovery if run else Decimal("0")),
            "otherDeductions": str(run.total_other_deductions if run else Decimal("0")),
            "deductions": str(run.total_deductions if run else Decimal("0")),
            "net": str(run.total_net if run else Decimal("0")),
        },
    }


def _previous_period(start: date) -> date:
    if start.month == 1:
        return date(start.year - 1, 12, 1)
    return date(start.year, start.month - 1, 1)


def payroll_period_context(*, company: Company, period_start: date, membership=None) -> dict[str, object]:
    start, _end = month_bounds(period_start)
    run = payroll_run_for_period(company=company, period_start=start)
    policy = payroll_policy_for_company(company=company)
    adjustments = payroll_adjustments_for_period(company=company, period_start=start)
    adjustments_by_employee: dict[str, list[dict[str, object]]] = {}
    for item in adjustments:
        adjustments_by_employee.setdefault(str(item.employee_id), []).append(serialize_payroll_adjustment(item))

    source_errors: list[str] = []
    if run is not None and run.status != PayrollRunStatus.DRAFT:
        rows = [_serialize_snapshot_line(item) for item in getattr(run, "payroll_lines", [])]
        if run.status in {PayrollRunStatus.CALCULATED, PayrollRunStatus.REVIEW}:
            try:
                verify_payroll_run_integrity(
                    company=company,
                    period_start=start,
                    verify_source=True,
                    require_locked_attendance=run.status == PayrollRunStatus.REVIEW,
                )
            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    source_errors = [str(message) for messages in exc.message_dict.values() for message in messages]
                else:
                    source_errors = [str(message) for message in exc.messages]
    else:
        try:
            preview = preview_payroll_run(company=company, period_start=start)
            rows = preview["rows"]
            source_errors = list(preview["blockers"])
        except ValidationError as exc:
            rows = []
            if hasattr(exc, "message_dict"):
                source_errors = [str(message) for messages in exc.message_dict.values() for message in messages]
            else:
                source_errors = [str(message) for message in exc.messages]

    approved_ids = {str(item.pk) for item in adjustments if item.status == PayrollAdjustmentStatus.APPROVED}
    pending_by_employee: dict[str, list[dict[str, object]]] = {}
    for item in adjustments:
        if str(item.pk) in approved_ids:
            continue
        pending_by_employee.setdefault(str(item.employee_id), []).append(serialize_payroll_adjustment(item))
    for row in rows:
        employee_id = str(row["employeeId"])
        pending = pending_by_employee.get(employee_id, [])
        row["pendingAdjustments"] = pending
        if pending:
            row.setdefault("warnings", []).append(f"{len(pending)} adjustment(s) are not approved and are excluded from payroll.")

    previous_start = _previous_period(start)
    previous_run = payroll_run_for_period(company=company, period_start=previous_start)
    previous_rows = [_serialize_snapshot_line(item) for item in getattr(previous_run, "payroll_lines", [])] if previous_run else []

    attendance_status = None
    if run and run.attendance_period:
        attendance_status = run.attendance_period.get_status_display()
    else:
        from apps.internal_payroll.selectors.attendance import attendance_period_for_company

        attendance = attendance_period_for_company(company=company, period_start=start)
        attendance_status = attendance.get_status_display() if attendance else "Not created"

    return {
        "run": _run_payload(run, period_start=start, membership=membership),
        "rows": rows,
        "sourceErrors": source_errors,
        "policy": serialize_payroll_policy(policy),
        "adjustments": [serialize_payroll_adjustment(item) for item in adjustments],
        "adjustmentsByEmployee": adjustments_by_employee,
        "reviewHistory": _audit_history(run),
        "attendanceStatus": attendance_status,
        "attendanceLocked": attendance_status == AttendancePeriodStatus.LOCKED.label,
        "previous": {
            "period": f"{previous_start:%Y-%m}",
            "label": _period_label(previous_start),
            "run": _run_payload(previous_run, period_start=previous_start, membership=membership) if previous_run else None,
            "rows": previous_rows,
        },
    }
