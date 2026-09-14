from __future__ import annotations

from calendar import month_name, monthrange
from datetime import date
from decimal import Decimal

from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Count, Prefetch, Q, Sum

from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.rental_manpower.project_adapter import rental_project_for_company, project_public_id
from apps.rental_manpower.models.settlements import EARNING_ADJUSTMENT_TYPES
from apps.rental_manpower.models import (
    RentalAdjustment, RentalAdjustmentEffect, RentalAdjustmentStatus, RentalAdjustmentType, RentalSettlementStatus,
    SupplierPayment, SupplierPaymentAllocation, SupplierPaymentStatus, SupplierSettlement,
    SupplierSettlementAdjustmentLine, SupplierSettlementLine, SupplierSettlementRateLine, RentalTimesheetEntry, RentalTimesheetPeriod, RentalTimesheetStatus,
    rental_adjustment_effect,
)

ZERO = Decimal("0.00")
PAYABLE_SETTLEMENT_STATUSES = {
    RentalSettlementStatus.APPROVED,
    RentalSettlementStatus.PAYMENT_PROCESSING,
    RentalSettlementStatus.PARTIALLY_PAID,
    RentalSettlementStatus.PAID,
    RentalSettlementStatus.CLOSED,
}


def _settlement_payable(settlement: SupplierSettlement) -> Decimal:
    return settlement.total_net if settlement.status in PAYABLE_SETTLEMENT_STATUSES else ZERO


def _month_bounds(period_start: date) -> tuple[date, date]:
    start = period_start.replace(day=1)
    return start, start.replace(day=monthrange(start.year, start.month)[1])


def _period_label(value: date) -> str:
    return f"{month_name[value.month]} {value.year}"


def _user_label(user) -> str:
    if user is None:
        return ""
    return user.get_full_name().strip() or user.username


def _rental_permissions(membership) -> dict[str, bool]:
    return {
        "edit": bool(membership and membership_can_edit(membership, Workspace.RENTAL)),
        "approve": bool(
            membership
            and membership_can_workspace(membership, Workspace.RENTAL)
            and membership_has_capability(membership, Capability.APPROVE)
        ),
        "pay": bool(
            membership
            and membership_can_workspace(membership, Workspace.RENTAL)
            and membership_has_capability(membership, Capability.PAY)
        ),
    }


def settlement_allowed_actions(settlement: SupplierSettlement, *, membership=None) -> list[str]:
    permissions = _rental_permissions(membership)
    actions: list[str] = []
    if settlement.status == RentalSettlementStatus.CALCULATED and permissions["edit"]:
        actions.extend(["calculate", "submit"])
    elif settlement.status == RentalSettlementStatus.REVIEW and permissions["approve"]:
        actions.extend(["return", "approve"])
    elif settlement.status in {
        RentalSettlementStatus.APPROVED,
        RentalSettlementStatus.PAYMENT_PROCESSING,
        RentalSettlementStatus.PARTIALLY_PAID,
    } and permissions["pay"]:
        _paid, processing = _payment_amounts(settlement)
        available = max(ZERO, settlement.total_net - _paid - processing)
        if available > ZERO:
            actions.append("pay")
    elif settlement.status == RentalSettlementStatus.PAID and permissions["pay"]:
        actions.append("close")
    return actions


def supplier_payment_allowed_actions(payment: SupplierPayment, *, membership=None) -> list[str]:
    permissions = _rental_permissions(membership)
    if not permissions["pay"]:
        return []
    if payment.status == SupplierPaymentStatus.PROCESSING:
        return ["paid", "failed", "cancelled"]
    if payment.status == SupplierPaymentStatus.PAID:
        return ["reversed"]
    if payment.status in {SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED}:
        return ["retry"]
    return []


def project_settlement_workflow(*, period: RentalTimesheetPeriod, settlements: list[SupplierSettlement], membership=None) -> dict[str, object]:
    permissions = _rental_permissions(membership)
    statuses = [row.status for row in settlements]
    all_status = lambda value: bool(statuses) and all(status == value for status in statuses)
    allowed: list[str] = []
    if permissions["edit"] and period.status == RentalTimesheetStatus.LOCKED and (not statuses or all(status in {RentalSettlementStatus.DRAFT, RentalSettlementStatus.CALCULATED} for status in statuses)):
        allowed.append("calculate")
    if permissions["edit"] and all_status(RentalSettlementStatus.CALCULATED):
        allowed.append("submit")
    if permissions["approve"] and all_status(RentalSettlementStatus.REVIEW):
        allowed.extend(["return", "approve"])
    if permissions["pay"] and all_status(RentalSettlementStatus.PAID):
        allowed.append("close")

    next_action = None
    for candidate in ("submit", "approve", "close", "calculate"):
        if candidate in allowed:
            next_action = candidate
            break
    return {
        "projectId": project_public_id(period.project),
        "timesheetStatus": period.get_status_display(),
        "timesheetStatusValue": period.status,
        "settlementStatuses": statuses,
        "allowedActions": allowed,
        "nextAction": next_action,
        "canCalculate": "calculate" in allowed,
        "canSubmit": "submit" in allowed,
        "canReturn": "return" in allowed,
        "canApprove": "approve" in allowed,
        "canClose": "close" in allowed,
    }


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




def _rental_adjustment_page_number(value: object) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _rental_adjustment_page_size(value: object) -> int:
    try:
        parsed = int(value or 50)
    except (TypeError, ValueError):
        parsed = 50
    return parsed if parsed in {25, 50, 100} else 50


def _rental_adjustment_choice(value: object, choices, field: str) -> str:
    raw = str(value or '').strip()
    if not raw or raw.lower() == 'all':
        return ''
    normalized = raw.lower().replace('-', '_').replace(' ', '_')
    for choice_value, choice_label in choices:
        if raw == choice_value or raw.lower() == str(choice_label).lower() or normalized == str(choice_value).lower():
            return str(choice_value)
    raise ValidationError({field: f'Select a valid {field} filter.'})


def _rental_adjustment_period_summary(*, company, period_start: date) -> dict[str, object]:
    start, _end = _month_bounds(period_start)
    queryset = RentalAdjustment.objects.for_company(company).filter(period_start=start)
    earning_types = list(EARNING_ADJUSTMENT_TYPES)
    values = queryset.aggregate(
        count=Count('pk'),
        earnings=Sum('amount', filter=Q(status=RentalAdjustmentStatus.APPROVED, adjustment_type__in=earning_types)),
        deductions=Sum('amount', filter=Q(status=RentalAdjustmentStatus.APPROVED) & ~Q(adjustment_type__in=earning_types)),
        pending=Count('pk', filter=~Q(status=RentalAdjustmentStatus.APPROVED)),
    )
    return {
        'count': int(values['count'] or 0),
        'earnings': str(values['earnings'] or ZERO),
        'deductions': str(values['deductions'] or ZERO),
        'advanceIssues': '0.00',
        'pending': int(values['pending'] or 0),
    }


def rental_adjustment_page_context(
    *, company, period_start: date, membership=None, page: object = 1, page_size: object = 50,
    search: str = '', adjustment_type: str = 'All', status: str = 'All',
    project_id: str = '', supplier_id: str = '', project_search: str = '', supplier_search: str = '',
) -> dict[str, object]:
    """Bounded Worker Adjustments register independent of the settlement mega-context.

    The live adjustments page must never hydrate settlements, payment allocations, timesheet
    scopes, or the complete adjustment month before pagination. Only the visible page gets
    related users/project data; exact KPI totals are database aggregates.
    """
    start, _end = _month_bounds(period_start)
    page_number = _rental_adjustment_page_number(page)
    size = _rental_adjustment_page_size(page_size)
    type_value = _rental_adjustment_choice(adjustment_type, RentalAdjustmentType.choices, 'type')
    status_value = _rental_adjustment_choice(status, RentalAdjustmentStatus.choices, 'status')
    queryset = RentalAdjustment.objects.for_company(company).filter(period_start=start)
    query = str(search or '').strip()
    if query:
        normalized_query = query.lower().replace(' ', '_')
        queryset = queryset.filter(
            Q(worker_name__icontains=query)
            | Q(worker_number__icontains=query)
            | Q(project_name__icontains=query)
            | Q(supplier_name__icontains=query)
            | Q(reason__icontains=query)
            | Q(reference__icontains=query)
            | Q(adjustment_type__icontains=normalized_query)
        )
    if type_value:
        queryset = queryset.filter(adjustment_type=type_value)
    if status_value:
        queryset = queryset.filter(status=status_value)
    if project_id and project_id != 'All projects':
        project = rental_project_for_company(company=company, identifier=project_id)
        queryset = queryset.filter(project_id=project.pk)
    if supplier_id and supplier_id != 'All suppliers':
        queryset = queryset.filter(supplier_id=supplier_id)
    project_query = str(project_search or '').strip()
    if project_query:
        queryset = queryset.filter(Q(project_name__icontains=project_query) | Q(project_code__icontains=project_query))
    supplier_query = str(supplier_search or '').strip()
    if supplier_query:
        queryset = queryset.filter(Q(supplier_name__icontains=supplier_query) | Q(supplier_code__icontains=supplier_query))
    queryset = queryset.select_related('project', 'submitted_by', 'approved_by').order_by('-transaction_date', '-created_at', '-pk')
    paginator = Paginator(queryset, size)
    page_obj = paginator.get_page(page_number)
    return {
        'surface': 'rental_adjustments_page',
        'period': f'{start:%Y-%m}',
        'view': 'register',
        'results': [serialize_rental_adjustment(item) for item in page_obj.object_list],
        'summary': _rental_adjustment_period_summary(company=company, period_start=start),
        'meta': {
            'count': paginator.count,
            'page': page_obj.number,
            'pageSize': size,
            'totalPages': paginator.num_pages,
            'rangeStart': page_obj.start_index() if paginator.count else 0,
            'rangeEnd': page_obj.end_index() if paginator.count else 0,
        },
        'filters': {
            'types': [{'value': value, 'label': label} for value, label in RentalAdjustmentType.choices],
            'statuses': [{'value': value, 'label': label} for value, label in RentalAdjustmentStatus.choices],
        },
        'canEdit': _rental_permissions(membership)['edit'],
        'canApprove': _rental_permissions(membership)['approve'],
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




def _financial_bucket() -> dict[str, object]:
    return {
        "workers": 0,
        "hours": ZERO,
        "otHours": ZERO,
        "base": ZERO,
        "otAmount": ZERO,
        "gross": ZERO,
        "adjustmentEarnings": ZERO,
        "adjustmentDeductions": ZERO,
        "advances": ZERO,
        "net": ZERO,
        "payable": ZERO,
        "paid": ZERO,
        "processing": ZERO,
        "outstanding": ZERO,
        "available": ZERO,
    }


def _add_financial_bucket(target: dict[str, object], settlement: SupplierSettlement, *, paid: Decimal, processing: Decimal, advances: Decimal) -> None:
    payable = _settlement_payable(settlement)
    outstanding = max(ZERO, payable - paid)
    available = max(ZERO, payable - paid - processing)
    target["workers"] = int(target["workers"]) + int(settlement.worker_count)
    target["hours"] += settlement.total_regular_hours
    target["otHours"] += settlement.total_overtime_hours
    target["base"] += settlement.total_base
    target["otAmount"] += settlement.total_overtime
    target["gross"] += settlement.total_gross
    target["adjustmentEarnings"] += settlement.total_adjustment_earnings
    target["adjustmentDeductions"] += settlement.total_adjustment_deductions
    target["advances"] += advances
    target["net"] += settlement.total_net
    target["payable"] += payable
    target["paid"] += paid
    target["processing"] += processing
    target["outstanding"] += outstanding
    target["available"] += available


def _settlement_advance_total(settlement: SupplierSettlement) -> Decimal:
    total = ZERO
    for line in getattr(settlement, "snapshot_lines", []):
        for adjustment in getattr(line, "snapshot_adjustment_lines", []):
            if adjustment.adjustment_type == "advance":
                total += adjustment.amount
    return total


def _serialize_financial_bucket(bucket: dict[str, object]) -> dict[str, object]:
    return {
        "workers": int(bucket["workers"]),
        "hours": str(bucket["hours"]),
        "otHours": str(bucket["otHours"]),
        "base": str(bucket["base"]),
        "otAmount": str(bucket["otAmount"]),
        "gross": str(bucket["gross"]),
        "adjustmentEarnings": str(bucket["adjustmentEarnings"]),
        "adjustmentDeductions": str(bucket["adjustmentDeductions"]),
        "advances": str(bucket["advances"]),
        "net": str(bucket["net"]),
        "payable": str(bucket["payable"]),
        "paid": str(bucket["paid"]),
        "processing": str(bucket["processing"]),
        "outstanding": str(bucket["outstanding"]),
        "available": str(bucket["available"]),
    }


def rental_financial_metrics_from_settlements(settlements: list[SupplierSettlement], *, advance_totals: dict[object, Decimal] | None = None) -> dict[str, object]:
    """Return the authoritative period financial roll-up used by Payroll UI surfaces.

    Settlement snapshot totals are the only cost authority. Payment allocations alter
    paid/processing/outstanding exposure but never recalculate settlement cost.
    """
    projects: dict[str, dict[str, object]] = {}
    suppliers: dict[str, dict[str, object]] = {}
    scopes: dict[str, dict[str, object]] = {}
    totals = _financial_bucket()

    for settlement in settlements:
        project_id = project_public_id(settlement.project)
        supplier_id = str(settlement.supplier_id)
        scope_key = f"{project_id}::{supplier_id}"
        paid, processing = _payment_amounts(settlement)
        advances = advance_totals.get(settlement.pk, ZERO) if advance_totals is not None else _settlement_advance_total(settlement)

        project_bucket = projects.setdefault(project_id, _financial_bucket())
        supplier_bucket = suppliers.setdefault(supplier_id, _financial_bucket())
        scope_bucket = scopes.setdefault(scope_key, _financial_bucket())
        for bucket in (project_bucket, supplier_bucket, scope_bucket, totals):
            _add_financial_bucket(bucket, settlement, paid=paid, processing=processing, advances=advances)

        scope_bucket["projectId"] = project_id
        scope_bucket["project"] = settlement.project_name
        scope_bucket["projectCode"] = settlement.project_code
        scope_bucket["supplierId"] = supplier_id
        scope_bucket["supplier"] = settlement.supplier_name
        scope_bucket["supplierCode"] = settlement.supplier_code
        scope_bucket["settlementId"] = str(settlement.pk)
        scope_bucket["settlementNumber"] = settlement.settlement_number
        scope_bucket["status"] = settlement.get_status_display()
        scope_bucket["statusValue"] = settlement.status

    project_payload = {key: _serialize_financial_bucket(value) for key, value in projects.items()}
    supplier_payload = {key: _serialize_financial_bucket(value) for key, value in suppliers.items()}
    scope_payload: dict[str, dict[str, object]] = {}
    for key, value in scopes.items():
        row = _serialize_financial_bucket(value)
        row.update({
            "projectId": value["projectId"],
            "project": value["project"],
            "projectCode": value["projectCode"],
            "supplierId": value["supplierId"],
            "supplier": value["supplier"],
            "supplierCode": value["supplierCode"],
            "settlementId": value["settlementId"],
            "settlementNumber": value["settlementNumber"],
            "status": value["status"],
            "statusValue": value["statusValue"],
        })
        scope_payload[key] = row

    return {
        "projects": project_payload,
        "suppliers": supplier_payload,
        "scopes": scope_payload,
        "totals": _serialize_financial_bucket(totals),
        "source": "Supplier settlement snapshots + supplier payment allocations",
    }


def rental_financial_metrics_for_period(*, company, period_start: date) -> dict[str, object]:
    start, _end = _month_bounds(period_start)
    allocation_qs = SupplierPaymentAllocation.objects.for_company(company).select_related("payment").order_by("created_at")
    settlements = list(
        SupplierSettlement.objects.for_company(company).filter(period_start=start)
        .select_related("project", "supplier")
        .prefetch_related(Prefetch("payment_allocations", queryset=allocation_qs, to_attr="snapshot_allocations"))
        .order_by("project_code", "supplier_code")
    )
    advance_rows = (
        SupplierSettlementAdjustmentLine.objects.for_company(company)
        .filter(
            settlement_line__settlement__period_start=start,
            adjustment_type="advance",
        )
        .values("settlement_line__settlement_id")
        .annotate(total=Sum("amount"))
    )
    advance_totals = {row["settlement_line__settlement_id"]: row["total"] or ZERO for row in advance_rows}
    return rental_financial_metrics_from_settlements(settlements, advance_totals=advance_totals)


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


def serialize_supplier_settlement(settlement: SupplierSettlement, *, membership=None) -> dict[str, object]:
    paid, processing = _payment_amounts(settlement)
    payable = _settlement_payable(settlement)
    outstanding = max(ZERO, payable - paid)
    available = max(ZERO, payable - paid - processing)
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
        "allowedActions": settlement_allowed_actions(settlement, membership=membership),
        "canGenerateSettlementDocument": settlement.status in PAYABLE_SETTLEMENT_STATUSES,
        "canGenerateInvoice": settlement.status in PAYABLE_SETTLEMENT_STATUSES,
        "totals": {
            "workers": settlement.worker_count, "hours": str(settlement.total_regular_hours), "workDays": settlement.total_work_days,
            "otHours": str(settlement.total_overtime_hours), "base": str(settlement.total_base), "otAmount": str(settlement.total_overtime),
            "gross": str(settlement.total_gross), "adjustmentEarnings": str(settlement.total_adjustment_earnings),
            "adjustments": str(settlement.total_adjustment_deductions), "net": str(settlement.total_net),
            "payable": str(payable), "paid": str(paid), "processing": str(processing), "outstanding": str(outstanding), "available": str(available),
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


def serialize_supplier_payment(payment: SupplierPayment, *, membership=None) -> dict[str, object]:
    allocations = getattr(payment, "snapshot_allocations", [])
    allowed_actions = supplier_payment_allowed_actions(payment, membership=membership)
    return {
        "id": str(payment.pk), "ref": payment.payment_number, "supplierId": str(payment.supplier_id), "supplier": payment.supplier_name,
        "date": payment.payment_date.isoformat(), "methodValue": payment.method, "method": payment.get_method_display(),
        "amount": str(payment.amount), "statusValue": payment.status, "status": payment.get_status_display(),
        "transactionReference": payment.transaction_reference, "note": payment.note, "resultReason": payment.result_reason,
        "paidAt": payment.paid_at.isoformat() if payment.paid_at else None, "reversedAt": payment.reversed_at.isoformat() if payment.reversed_at else None,
        "cancelledAt": payment.cancelled_at.isoformat() if payment.cancelled_at else None,
        "retryOf": str(payment.retry_of_id) if payment.retry_of_id else None,
        "allowedActions": allowed_actions,
        "nextAction": (allowed_actions or [None])[0],
        "canRetry": "retry" in allowed_actions,
        "canGenerateReceipt": payment.status == SupplierPaymentStatus.PAID,
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
    adjustments_by_worker: dict[str, list[dict[str, object]]] = {}
    for adjustment in adjustments:
        adjustments_by_worker.setdefault(str(adjustment.worker_id), []).append(serialize_rental_adjustment(adjustment))
    payments = supplier_payments_for_period(company=company, period_start=start)
    timesheet_scopes = []
    project_workflows: dict[str, dict[str, object]] = {}
    periods = list(RentalTimesheetPeriod.objects.for_company(company).filter(period_start=start).select_related("project").order_by("project__code"))
    period_ids = [item.pk for item in periods]
    supplier_scope_rows = list(
        RentalTimesheetEntry.objects.for_company(company).filter(period_id__in=period_ids)
        .values("period_id", "worker__supplier_id", "worker__supplier__code", "worker__supplier__name").distinct()
        .order_by("period_id", "worker__supplier__code")
    ) if period_ids else []
    suppliers_by_period: dict[object, list[dict[str, object]]] = {}
    for row in supplier_scope_rows:
        suppliers_by_period.setdefault(row["period_id"], []).append(row)
    settlements_by_project: dict[object, list[SupplierSettlement]] = {}
    for settlement in settlements:
        settlements_by_project.setdefault(settlement.project_id, []).append(settlement)
    for ts_period in periods:
        supplier_rows = suppliers_by_period.get(ts_period.pk, [])
        timesheet_scopes.append({
            "projectId": project_public_id(ts_period.project), "project": ts_period.project.name, "projectCode": ts_period.project.code,
            "statusValue": ts_period.status, "status": ts_period.get_status_display(), "revision": ts_period.revision,
            "suppliers": [{"id": str(row["worker__supplier_id"]), "code": row["worker__supplier__code"], "name": row["worker__supplier__name"]} for row in supplier_rows],
        })
        project_workflows[project_public_id(ts_period.project)] = project_settlement_workflow(
            period=ts_period, settlements=settlements_by_project.get(ts_period.project_id, []), membership=membership
        )
    financial_metrics = rental_financial_metrics_from_settlements(settlements)
    return {
        "period": f"{start:%Y-%m}", "label": _period_label(start),
        "settlements": [serialize_supplier_settlement(row, membership=membership) for row in settlements],
        "financialMetrics": financial_metrics,
        "adjustments": [serialize_rental_adjustment(row) for row in adjustments],
        "adjustmentsByWorker": adjustments_by_worker,
        "payments": [serialize_supplier_payment(row, membership=membership) for row in payments],
        "timesheetScopes": timesheet_scopes,
        "projectWorkflows": project_workflows,
        "canEdit": _rental_permissions(membership)["edit"],
        "canApprove": _rental_permissions(membership)["approve"],
        "canPay": _rental_permissions(membership)["pay"],
    }
