from __future__ import annotations

from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from apps.core.models import AuditEvent
from apps.internal_payroll.models import (
    EmploymentStatus,
    InternalEmployee,
    PayrollAdjustment,
    PayrollAdjustmentStatus,
    PayrollRun,
    PayrollRunStatus,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
)
from apps.rental_manpower.models import (
    RentalAdjustment,
    RentalAdjustmentStatus,
    RentalSettlementStatus,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierPaymentStatus,
    SupplierSettlement,
    WorkerAssignment,
)


ZERO = Decimal("0")
FINAL_INTERNAL = {
    PayrollRunStatus.APPROVED,
    PayrollRunStatus.PAYMENT_PROCESSING,
    PayrollRunStatus.PAID,
    PayrollRunStatus.CLOSED,
}
FINAL_RENTAL = {
    RentalSettlementStatus.APPROVED,
    RentalSettlementStatus.PAYMENT_PROCESSING,
    RentalSettlementStatus.PARTIALLY_PAID,
    RentalSettlementStatus.PAID,
    RentalSettlementStatus.CLOSED,
}


def _money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def _internal_summary(company, period_start):
    run = PayrollRun.objects.for_company(company).filter(period_start=period_start).first()
    if not run:
        return {"exists": False, "status": "Not calculated", "finalized": False, "employees": 0, "gross": "0.00", "deductions": "0.00", "net": "0.00"}
    return {
        "exists": True,
        "id": str(run.id),
        "status": run.get_status_display(),
        "statusValue": run.status,
        "finalized": run.status in FINAL_INTERNAL,
        "employees": run.employee_count,
        "gross": _money(run.total_gross),
        "deductions": _money(run.total_deductions),
        "net": _money(run.total_net),
    }


def _rental_summary(company, period_start):
    qs = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL)
    values = qs.aggregate(
        gross=Sum("total_gross"),
        adjustments_earn=Sum("total_adjustment_earnings"),
        adjustments_ded=Sum("total_adjustment_deductions"),
        net=Sum("total_net"),
        workers=Sum("worker_count"),
    )
    return {
        "records": qs.count(),
        "finalized": qs.exists(),
        "workers": int(values["workers"] or 0),
        "gross": _money(values["gross"]),
        "adjustmentEarnings": _money(values["adjustments_earn"]),
        "adjustmentDeductions": _money(values["adjustments_ded"]),
        "net": _money(values["net"]),
    }


def _internal_payment(company, period_start):
    qs = SalaryPaymentRow.objects.for_company(company).filter(batch__run__period_start=period_start, claim_active=True)
    total = qs.aggregate(value=Sum("amount"))["value"] or ZERO
    paid = qs.filter(status=SalaryPaymentRowStatus.PAID).aggregate(value=Sum("amount"))["value"] or ZERO
    failed = qs.filter(status__in=[SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED]).count()
    return {"records": qs.count(), "total": _money(total), "paid": _money(paid), "pending": _money(max(ZERO, total - paid)), "failed": failed}


def _rental_payment(company, period_start):
    settlements = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL)
    total = settlements.aggregate(value=Sum("total_net"))["value"] or ZERO
    allocations = SupplierPaymentAllocation.objects.for_company(company).filter(settlement__in=settlements)
    paid = allocations.filter(payment__status=SupplierPaymentStatus.PAID).aggregate(value=Sum("amount"))["value"] or ZERO
    processing = allocations.filter(payment__status=SupplierPaymentStatus.PROCESSING).aggregate(value=Sum("amount"))["value"] or ZERO
    failures = SupplierPayment.objects.for_company(company).filter(
        allocations__settlement__in=settlements,
        status__in=[SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED],
    ).distinct().count()
    return {
        "total": _money(total),
        "paid": _money(paid),
        "processing": _money(processing),
        "outstanding": _money(max(ZERO, total - paid)),
        "available": _money(max(ZERO, total - paid - processing)),
        "failed": failures,
    }


def _approval_items(company):
    currency = company.settings.currency_code
    rows: list[dict[str, object]] = []
    for run in PayrollRun.objects.for_company(company).filter(status__in=[PayrollRunStatus.CALCULATED, PayrollRunStatus.REVIEW]).order_by("-period_start")[:100]:
        rows.append({
            "id": f"payroll-{run.id}", "workspace": "internal", "route": "payroll-runs", "period": run.period_start.strftime("%B %Y"),
            "type": "Internal Payroll", "severity": "Review", "title": f"{run.period_start:%B %Y} payroll · {run.get_status_display()}",
            "detail": "Payroll is waiting for the next controlled review or approval action.",
        })
    for adjustment in PayrollAdjustment.objects.for_company(company).select_related("employee").filter(status=PayrollAdjustmentStatus.REVIEW).order_by("-transaction_date")[:100]:
        rows.append({
            "id": f"internal-adjustment-{adjustment.id}", "workspace": "internal", "route": "adjustments", "period": adjustment.period_start.strftime("%B %Y"),
            "type": "Adjustment", "severity": "Review", "title": f"{adjustment.employee.full_name} · {adjustment.get_adjustment_type_display()}",
            "detail": f"{currency} {_money(adjustment.amount)} adjustment is waiting for approval.",
        })
    for payment in SalaryPaymentRow.objects.for_company(company).filter(claim_active=True, status__in=[SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED]).select_related("batch__run").order_by("-last_result_at")[:100]:
        rows.append({
            "id": f"salary-payment-{payment.id}", "workspace": "internal", "route": "payments", "period": payment.batch.run.period_start.strftime("%B %Y"),
            "type": "Payment", "severity": "Critical", "title": f"Salary payment {payment.get_status_display().lower()} · {payment.employee_name}",
            "detail": f"{currency} {_money(payment.amount)} · {payment.failure_reason or 'Payment requires reconciliation or retry.'}",
        })
    for settlement in SupplierSettlement.objects.for_company(company).filter(status__in=[RentalSettlementStatus.CALCULATED, RentalSettlementStatus.REVIEW]).order_by("-period_start")[:100]:
        rows.append({
            "id": f"settlement-{settlement.id}", "workspace": "rental", "route": "rental-settlements", "period": settlement.period_start.strftime("%B %Y"),
            "type": "Rental Settlement", "severity": "Review", "title": f"{settlement.supplier_name} · {settlement.get_status_display()}",
            "detail": f"{settlement.project_name} · {currency} {_money(settlement.total_net)} net settlement is awaiting the next controlled step.",
        })
    for adjustment in RentalAdjustment.objects.for_company(company).select_related("worker").filter(status=RentalAdjustmentStatus.REVIEW).order_by("-transaction_date")[:100]:
        rows.append({
            "id": f"rental-adjustment-{adjustment.id}", "workspace": "rental", "route": "adjustments", "period": adjustment.period_start.strftime("%B %Y"),
            "type": "Adjustment", "severity": "Review", "title": f"{adjustment.worker.full_name} · {adjustment.get_adjustment_type_display()}",
            "detail": f"{currency} {_money(adjustment.amount)} rental adjustment is waiting for approval.",
        })
    for payment in SupplierPayment.objects.for_company(company).filter(status__in=[SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED]).order_by("-payment_date")[:100]:
        rows.append({
            "id": f"supplier-payment-{payment.id}", "workspace": "rental", "route": "payments", "period": "",
            "type": "Payment", "severity": "Critical", "title": f"Supplier payment {payment.get_status_display().lower()} · {payment.supplier_name}",
            "detail": f"{currency} {_money(payment.amount)} · {payment.result_reason or 'Supplier payment requires review.'}",
        })
    severity_order = {"Critical": 0, "Review": 1}
    rows.sort(key=lambda row: (severity_order.get(str(row["severity"]), 9), str(row.get("period") or "")), reverse=False)
    return rows[:300]


def _audit_rows(company, *, limit=300):
    events = AuditEvent.objects.filter(company=company).order_by("-created_at")[:limit]
    rows = []
    for item in events:
        workspace = "rental" if item.area == "rental" else "internal" if item.area == "internal" else "management"
        metadata = item.metadata if isinstance(item.metadata, dict) else {}
        period = str(metadata.get("period") or metadata.get("period_start") or "")
        detail = item.object_label or str(metadata.get("detail") or "")
        rows.append({
            "id": str(item.id),
            "workspace": workspace,
            "area": item.area,
            "type": item.object_type,
            "period": period,
            "date": item.created_at.isoformat(),
            "actor": item.actor_display_name or item.actor_username or "System",
            "role": item.actor_role,
            "action": item.action,
            "detail": detail,
            "objectId": item.object_id,
            "requestId": str(item.request_id) if item.request_id else "",
        })
    return rows


def management_periods(company):
    periods = set(PayrollRun.objects.for_company(company).values_list("period_start", flat=True))
    periods.update(SupplierSettlement.objects.for_company(company).values_list("period_start", flat=True))
    return sorted(periods, reverse=True)


def management_context(*, company, period_start):
    today = timezone.localdate()
    internal = _internal_summary(company, period_start)
    rental = _rental_summary(company, period_start)
    internal_net = Decimal(internal["net"])
    rental_net = Decimal(rental["net"])
    comparable = bool(internal["finalized"] and rental["finalized"])
    internal_headcount = InternalEmployee.objects.for_company(company).filter(status__in=[EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE]).count()
    rental_headcount = WorkerAssignment.objects.for_company(company).filter(
        cancelled_at__isnull=True,
        effective_from__lte=today,
    ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=today)).values("worker_id").distinct().count()
    approvals = _approval_items(company)
    return {
        "period": period_start.strftime("%Y-%m"),
        "periodLabel": period_start.strftime("%B %Y"),
        "availablePeriods": [{"key": item.strftime("%Y-%m"), "label": item.strftime("%B %Y")} for item in management_periods(company)],
        "internal": internal,
        "rental": rental,
        "combined": _money(internal_net + rental_net) if comparable else None,
        "comparable": comparable,
        "headcount": {"internal": internal_headcount, "rental": rental_headcount, "total": internal_headcount + rental_headcount},
        "payments": {"internal": _internal_payment(company, period_start), "rental": _rental_payment(company, period_start)},
        "approvals": approvals,
        "audit": _audit_rows(company),
    }
