from __future__ import annotations

from calendar import month_name, monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Sum

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id
from apps.rental_manpower.models import (
    RentalAdjustment, RentalAdjustmentEffect, RentalAdjustmentStatus, RentalSettlementStatus,
    SupplierPayment, SupplierPaymentAllocation, SupplierPaymentStatus, SupplierSettlement,
    SupplierSettlementAdjustmentLine, SupplierSettlementLine, SupplierSettlementRateLine, RentalTimesheetEntry, RentalTimesheetPeriod,
    rental_adjustment_effect,
)

ZERO = Decimal("0.00")


def _month_bounds(period_start: date) -> tuple[date, date]:
    start = period_start.replace(day=1)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


def _period_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _user_label(user) -> str:
    if user is None:
        return ""
    return user.get_full_name().strip() or user.username


def serialize_rental_adjustment(item: RentalAdjustment) -> dict[str, object]:
    effect = rental_adjustment_effect(item.adjustment_type)
    return {
        "id": str(item.pk), "workerId": str(item.worker_id), "personId": str(item.worker_id),
        "personCode": item.worker_number, "personName": item.worker_name,
        "supplierId": str(item.supplier_id), "supplier": item.supplier_name,
        "projectId": project_public_id(item.project), "project": item.project_name,
        "assignmentId": str(item.assignment_id), "trade": item.trade,
        "rateType": item.get_rate_type_display(), "rate": str(item.rate),
        "date": item.transaction_date.isoformat(), "period": _period_label(item.period_start),
        "periodKey": f"{item.period_start:%Y-%m}", "typeCode": item.adjustment_type,
        "type": item.get_adjustment_type_display(), "amount": str(item.amount), "reason": item.reason,
        "reference": item.reference, "statusValue": item.status, "status": item.get_status_display(),
        "effectValue": effect, "impact": RentalAdjustmentEffect(effect).label,
        "submittedAt": item.submitted_at.isoformat() if item.submitted_at else None,
        "submittedBy": _user_label(item.submitted_by), "approvedAt": item.approved_at.isoformat() if item.approved_at else None,
        "approvedBy": _user_label(item.approved_by), "immutable": item.status == RentalAdjustmentStatus.APPROVED,
        "source": "Company database", "workforce": "Rental Manpower", "workforceKey": "Rental",
    }


def rental_adjustments_for_period(*, company, period_start: date) -> list[RentalAdjustment]:
    start, _end = _month_bounds(period_start)
    return list(
        RentalAdjustment.objects.for_company(company).filter(period_start=start)
        .select_related("worker", "supplier", "project", "assignment", "submitted_by", "approved_by")
        .order_by("-transaction_date", "-created_at")
    )


def rental_adjustments_by_worker(*, company, period_start: date) -> dict[str, list[dict[str, object]]]:
    result: dict[str, list[dict[str, object]]] = {}
    for item in rental_adjustments_for_period(company=company, period_start=period_start):
        result.setdefault(str(item.worker_id), []).append(serialize_rental_adjustment(item))
    return result


def _settlement_queryset(company):
    rate_qs = SupplierSettlementRateLine.objects.for_company(company).select_related("assignment").order_by("effective_from", "created_at")
    adjustment_qs = SupplierSettlementAdjustmentLine.objects.for_company(company).select_related("adjustment").order_by("transaction_date", "created_at")
    line_qs = (
        SupplierSettlementLine.objects.for_company(company).select_related("worker")
        .prefetch_related(
            Prefetch("rate_lines", queryset=rate_qs, to_attr="snapshot_rate_lines"),
            Prefetch("adjustment_lines", queryset=adjustment_qs, to_attr="snapshot_adjustment_lines"),
        ).order_by("worker_number", "worker_name")
    )
    allocation_qs = SupplierPaymentAllocation.objects.for_company(company).select_related("payment").order_by("created_at")
    return (
        SupplierSettlement.objects.for_company(company)
        .select_related("project", "supplier", "source_timesheet", "calculated_by", "submitted_by", "approved_by", "closed_by")
        .prefetch_related(Prefetch("lines", queryset=line_qs, to_attr="snapshot_lines"), Prefetch("payment_allocations", queryset=allocation_qs, to_attr="snapshot_allocations"))
    )


def _payment_amounts(settlement: SupplierSettlement) -> tuple[Decimal, Decimal]:
    paid = ZERO; processing = ZERO
    for allocation in getattr(settlement, "snapshot_allocations", []):
        if allocation.payment.status == SupplierPaymentStatus.PAID:
            paid += allocation.amount
        elif allocation.payment.status == SupplierPaymentStatus.PROCESSING:
            processing += allocation.amount
    return paid, processing


def serialize_settlement_line(line: SupplierSettlementLine) -> dict[str, object]:
    return {
        "id": str(line.pk), "workerId": str(line.worker_id), "workerCode": line.worker_number, "name": line.worker_name,
        "supplier": line.supplier_name, "project": line.project_name, "trade": line.trade_summary, "rate": line.rate_summary,
        "assignmentCount": len(getattr(line, "snapshot_rate_lines", [])),
        "hours": str(line.regular_hours), "workDays": line.work_days, "otHours": str(line.overtime_hours),
        "base": str(line.base_amount), "otAmount": str(line.overtime_amount), "gross": str(line.gross_amount),
        "adjustmentEarnings": str(line.adjustment_earnings), "adjustments": str(line.adjustment_deductions), "net": str(line.net_amount),
        "rateLines": [
            {
                "assignmentId": str(rate.assignment_id), "effectiveFrom": rate.effective_from.isoformat(), "effectiveTo": rate.effective_to.isoformat(),
                "trade": rate.trade, "rateTypeValue": rate.rate_type, "rateType": rate.get_rate_type_display(), "rate": str(rate.rate),
                "regularHours": str(rate.regular_hours), "billableDays": rate.billable_days, "calendarDays": rate.calendar_days, "base": str(rate.base_amount),
            }
            for rate in getattr(line, "snapshot_rate_lines", [])
        ],
        "adjustmentLines": [
            {
                "adjustmentId": str(adj.adjustment_id), "typeCode": adj.adjustment_type, "type": adj.adjustment_label,
                "effect": adj.effect, "amount": str(adj.amount), "reason": adj.reason, "reference": adj.reference,
                "date": adj.transaction_date.isoformat(),
            }
            for adj in getattr(line, "snapshot_adjustment_lines", [])
        ],
    }


def serialize_supplier_settlement(settlement: SupplierSettlement) -> dict[str, object]:
    paid, processing = _payment_amounts(settlement)
    outstanding = max(ZERO, settlement.total_net - paid)
    available = max(ZERO, settlement.total_net - paid - processing)
    return {
        "id": str(settlement.pk), "number": settlement.settlement_number,
        "period": _period_label(settlement.period_start), "periodKey": f"{settlement.period_start:%Y-%m}",
        "projectId": project_public_id(settlement.project), "project": settlement.project_name, "projectCode": settlement.project_code,
        "supplierId": str(settlement.supplier_id), "supplier": settlement.supplier_name, "supplierCode": settlement.supplier_code,
        "statusValue": settlement.status, "status": settlement.get_status_display(), "revision": settlement.revision,
        "sourceTimesheetId": str(settlement.source_timesheet_id), "sourceTimesheetRevision": settlement.source_timesheet_revision,
        "sourceTimesheetStatus": settlement.source_timesheet.get_status_display(),
        "calculatedAt": settlement.calculated_at.isoformat() if settlement.calculated_at else None, "calculatedBy": _user_label(settlement.calculated_by),
        "submittedAt": settlement.submitted_at.isoformat() if settlement.submitted_at else None, "submittedBy": _user_label(settlement.submitted_by),
        "approvedAt": settlement.approved_at.isoformat() if settlement.approved_at else None, "approvedBy": _user_label(settlement.approved_by),
        "reviewerNote": settlement.reviewer_note, "closedAt": settlement.closed_at.isoformat() if settlement.closed_at else None,
        "totals": {
            "workers": settlement.worker_count, "hours": str(settlement.total_regular_hours), "workDays": settlement.total_work_days,
            "otHours": str(settlement.total_overtime_hours), "base": str(settlement.total_base), "otAmount": str(settlement.total_overtime),
            "gross": str(settlement.total_gross), "adjustmentEarnings": str(settlement.total_adjustment_earnings),
            "adjustments": str(settlement.total_adjustment_deductions), "net": str(settlement.total_net),
            "paid": str(paid), "processing": str(processing), "outstanding": str(outstanding), "available": str(available),
        },
        "rows": [serialize_settlement_line(line) for line in getattr(settlement, "snapshot_lines", [])],
        "preview": False,
    }


def settlements_for_period(*, company, period_start: date, project_id=None, supplier_id=None) -> list[SupplierSettlement]:
    start, _end = _month_bounds(period_start)
    qs = _settlement_queryset(company).filter(period_start=start)
    if project_id:
        project = rental_project_for_company(company=company, identifier=project_id)
        qs = qs.filter(project=project)
    if supplier_id:
        qs = qs.filter(supplier_id=supplier_id)
    return list(qs.order_by("project_code", "supplier_code"))


def serialize_supplier_payment(payment: SupplierPayment) -> dict[str, object]:
    allocations = getattr(payment, "snapshot_allocations", [])
    return {
        "id": str(payment.pk), "ref": payment.payment_number, "supplierId": str(payment.supplier_id), "supplier": payment.supplier_name,
        "date": payment.payment_date.isoformat(), "methodValue": payment.method, "method": payment.get_method_display(),
        "amount": str(payment.amount), "statusValue": payment.status, "status": payment.get_status_display(),
        "transactionReference": payment.transaction_reference, "note": payment.note, "resultReason": payment.result_reason,
        "paidAt": payment.paid_at.isoformat() if payment.paid_at else None, "reversedAt": payment.reversed_at.isoformat() if payment.reversed_at else None,
        "cancelledAt": payment.cancelled_at.isoformat() if payment.cancelled_at else None,
        "retryOf": str(payment.retry_of_id) if payment.retry_of_id else None,
        "allocations": [
            {
                "id": str(item.pk), "settlementId": str(item.settlement_id), "settlementNumber": item.settlement.settlement_number,
                "period": _period_label(item.settlement.period_start), "projectId": project_public_id(item.settlement.project), "project": item.settlement.project_name,
                "amount": str(item.amount),
            }
            for item in allocations
        ],
    }


def supplier_payments_for_period(*, company, period_start: date) -> list[SupplierPayment]:
    start, _end = _month_bounds(period_start)
    allocations = SupplierPaymentAllocation.objects.for_company(company).select_related("settlement").filter(settlement__period_start=start).order_by("created_at")
    payments = (
        SupplierPayment.objects.for_company(company).filter(allocations__settlement__period_start=start).distinct()
        .select_related("supplier", "retry_of")
        .prefetch_related(Prefetch("allocations", queryset=allocations, to_attr="snapshot_allocations"))
        .order_by("-payment_date", "-created_at")
    )
    return list(payments)


def rental_settlement_context(*, company, period_start: date, membership=None, project_id=None, supplier_id=None) -> dict[str, object]:
    start, _end = _month_bounds(period_start)
    settlements = settlements_for_period(company=company, period_start=start, project_id=project_id, supplier_id=supplier_id)
    adjustments = rental_adjustments_for_period(company=company, period_start=start)
    payments = supplier_payments_for_period(company=company, period_start=start)
    timesheet_scopes = []
    periods = RentalTimesheetPeriod.objects.for_company(company).filter(period_start=start).select_related("project").order_by("project__code")
    for ts_period in periods:
        supplier_rows = list(
            RentalTimesheetEntry.objects.for_company(company).filter(period=ts_period)
            .values("worker__supplier_id", "worker__supplier__code", "worker__supplier__name").distinct()
            .order_by("worker__supplier__code")
        )
        timesheet_scopes.append({
            "projectId": project_public_id(ts_period.project), "project": ts_period.project.name, "projectCode": ts_period.project.code,
            "statusValue": ts_period.status, "status": ts_period.get_status_display(), "revision": ts_period.revision,
            "suppliers": [{"id": str(row["worker__supplier_id"]), "code": row["worker__supplier__code"], "name": row["worker__supplier__name"]} for row in supplier_rows],
        })
    return {
        "period": f"{start:%Y-%m}", "label": _period_label(start),
        "settlements": [serialize_supplier_settlement(row) for row in settlements],
        "adjustments": [serialize_rental_adjustment(row) for row in adjustments],
        "adjustmentsByWorker": rental_adjustments_by_worker(company=company, period_start=start),
        "payments": [serialize_supplier_payment(row) for row in payments],
        "timesheetScopes": timesheet_scopes,
        "canEdit": bool(membership and membership_can_edit(membership, Workspace.RENTAL)),
        "canApprove": bool(membership and membership_can_workspace(membership, Workspace.RENTAL) and membership_has_capability(membership, Capability.APPROVE)),
        "canPay": bool(membership and membership_can_workspace(membership, Workspace.RENTAL) and membership_has_capability(membership, Capability.PAY)),
    }
