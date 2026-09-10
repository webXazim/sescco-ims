from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from apps.internal_payroll.models import (
    EmployeePaymentProfile,
    PayrollAdjustment,
    PayrollRun,
    PayrollRunLine,
    PayrollRunStatus,
    SalaryPaymentRow,
)
from apps.rental_manpower.models import (
    RentalAdjustment,
    RentalSettlementStatus,
    SupplierPaymentAllocation,
    SupplierSettlement,
    SupplierSettlementLine,
    WorkerAssignment,
)

from .selectors import FINAL_INTERNAL, FINAL_RENTAL


ZERO = Decimal("0")


def _money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def _hours(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def available_report_periods(company):
    periods = set(PayrollRun.objects.for_company(company).values_list("period_start", flat=True))
    periods.update(SupplierSettlement.objects.for_company(company).values_list("period_start", flat=True))
    return sorted(periods, reverse=True)


def _run(company, period_start):
    return PayrollRun.objects.for_company(company).filter(period_start=period_start).first()


def _internal_payroll(company, period_start):
    run = _run(company, period_start)
    rows = []
    if run:
        for item in PayrollRunLine.objects.for_company(company).filter(run=run).order_by("employee_number"):
            rows.append([item.employee_number, item.employee_name, item.branch_name, item.department_name, item.position, _money(item.basic), _money(item.overtime_amount), _money(item.gross), _money(item.total_deductions), _money(item.net)])
    return {
        "title": "Internal Payroll",
        "description": "Employee payroll snapshot by internal organization.",
        "columns": ["Employee ID", "Employee", "Branch", "Department", "Position", "Basic", "OT", "Gross", "Deductions", "Net"],
        "rows": rows,
        "kpis": [["Employees", len(rows)], ["Gross", _money(run.total_gross if run else 0)], ["Deductions", _money(run.total_deductions if run else 0)], ["Net", _money(run.total_net if run else 0)]],
        "sourceNote": f"Uses the stored payroll snapshot for {period_start:%B %Y}. Status: {run.get_status_display() if run else 'Not calculated'}.",
    }


def _rental_group(company, period_start, *, by_supplier=False):
    qs = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL)
    grouped = defaultdict(lambda: {"count": 0, "workers": 0, "hours": ZERO, "ot": ZERO, "gross": ZERO, "deductions": ZERO, "net": ZERO})
    labels = {}
    for item in qs:
        key = str(item.supplier_id if by_supplier else item.project_id)
        labels[key] = item.supplier_name if by_supplier else item.project_name
        row = grouped[key]
        row["count"] += 1
        row["workers"] += item.worker_count
        row["hours"] += item.total_regular_hours
        row["ot"] += item.total_overtime_hours
        row["gross"] += item.total_gross + item.total_adjustment_earnings
        row["deductions"] += item.total_adjustment_deductions
        row["net"] += item.total_net
    rows = [[labels[key], value["count"], value["workers"], _hours(value["hours"]), _hours(value["ot"]), _money(value["gross"]), _money(value["deductions"]), _money(value["net"])] for key, value in sorted(grouped.items(), key=lambda pair: labels[pair[0]].casefold())]
    net = sum((value["net"] for value in grouped.values()), ZERO)
    return {
        "title": "Supplier Cost" if by_supplier else "Project Manpower Cost",
        "description": "Approved rental manpower cost grouped by supplier." if by_supplier else "Approved rental manpower cost grouped by project.",
        "columns": ["Supplier" if by_supplier else "Project", "Settlements", "Workers", "Hours", "OT Hours", "Gross + Earnings", "Deductions", "Net Cost"],
        "rows": rows,
        "kpis": [["Groups", len(rows)], ["Settlements", qs.count()], ["Workers", sum(value["workers"] for value in grouped.values())], ["Net Cost", _money(net)]],
        "sourceNote": "Uses Approved or later supplier-settlement snapshots only; draft/review values are excluded.",
    }


def _overtime(company, period_start, workspace):
    rows = []
    if workspace in {"internal", "management"}:
        run = _run(company, period_start)
        if run:
            for item in PayrollRunLine.objects.for_company(company).filter(run=run, overtime_hours__gt=0).order_by("employee_number"):
                rows.append(["Internal", item.employee_number, item.employee_name, item.branch_name, _hours(item.overtime_hours), str(item.overtime_rate or ""), _money(item.overtime_amount)])
    if workspace in {"rental", "management"}:
        for item in SupplierSettlementLine.objects.for_company(company).filter(settlement__period_start=period_start, settlement__status__in=FINAL_RENTAL, overtime_hours__gt=0).select_related("settlement").order_by("worker_number"):
            rows.append(["Rental", item.worker_number, item.worker_name, item.settlement.project_name, _hours(item.overtime_hours), "Snapshot", _money(item.overtime_amount)])
    total = sum((Decimal(row[6]) for row in rows), ZERO)
    hours = sum((Decimal(row[4]) for row in rows), ZERO)
    return {"title": "Overtime", "description": "Overtime captured in controlled payroll/settlement snapshots.", "columns": ["Workforce", "ID", "Name", "Branch / Project", "OT Hours", "Rate", "OT Amount"], "rows": rows, "kpis": [["Records", len(rows)], ["OT Hours", _hours(hours)], ["OT Amount", _money(total)], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "Internal values come from payroll snapshots; rental values come from approved supplier-settlement snapshots."}


def _adjustments(company, period_start, workspace):
    rows = []
    if workspace == "internal":
        for item in PayrollAdjustment.objects.for_company(company).filter(period_start=period_start).select_related("employee").order_by("transaction_date"):
            rows.append([item.employee.employee_number, item.employee.full_name, item.get_adjustment_type_display(), item.transaction_date.isoformat(), _money(item.amount), item.get_status_display(), item.reference, item.reason])
    else:
        for item in RentalAdjustment.objects.for_company(company).filter(period_start=period_start).select_related("worker", "project", "supplier").order_by("transaction_date"):
            rows.append([item.worker.worker_number, item.worker.full_name, item.get_adjustment_type_display(), item.transaction_date.isoformat(), _money(item.amount), item.get_status_display(), item.reference, item.reason])
    amount = sum((Decimal(row[4]) for row in rows), ZERO)
    return {"title": "Advances & Adjustments", "description": "Period adjustment ledger with workflow status.", "columns": ["ID", "Person", "Type", "Date", "Amount", "Status", "Reference", "Reason"], "rows": rows, "kpis": [["Transactions", len(rows)], ["Amount", _money(amount)], ["Period", period_start.strftime("%B %Y")], ["Workspace", "Internal Company" if workspace == "internal" else "Rental Manpower"]], "sourceNote": "This report reads the transaction ledger; Approved status determines inclusion in financial calculation snapshots."}


def _transfers(company, period_start):
    end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    qs = WorkerAssignment.objects.for_company(company).filter(cancelled_at__isnull=True, effective_from__range=(period_start, end)).select_related("worker", "project").order_by("effective_from", "worker__worker_number")
    rows = [[item.worker.worker_number, item.worker.full_name, item.project.code, item.project.name, item.get_change_type_display(), item.trade, item.get_rate_type_display(), str(item.rate), item.effective_from.isoformat(), item.effective_to.isoformat() if item.effective_to else ""] for item in qs]
    return {"title": "Worker Transfers & Assignment Changes", "description": "Effective-dated rental assignment lifecycle changes.", "columns": ["Worker ID", "Worker", "Project Code", "Project", "Change", "Trade", "Rate Type", "Rate", "Effective From", "Effective To"], "rows": rows, "kpis": [["Changes", len(rows)], ["Period", period_start.strftime("%B %Y")], ["Transfers", sum(1 for row in rows if row[4] == "Project transfer")], ["Rate Changes", sum(1 for row in rows if row[4] == "Rate change")]], "sourceNote": "Reads immutable/effective-dated effective-dated assignment segments; cancelled scheduled changes are excluded."}


def _payments(company, period_start, workspace):
    rows = []
    if workspace == "internal":
        qs = SalaryPaymentRow.objects.for_company(company).filter(batch__run__period_start=period_start).select_related("batch").order_by("employee_number", "batch__prepared_at")
        for item in qs:
            rows.append([item.employee_number, item.employee_name, item.batch.reference, item.batch.get_channel_display(), _money(item.amount), item.get_status_display(), item.transaction_reference, item.paid_at.isoformat() if item.paid_at else ""])
    else:
        qs = SupplierPaymentAllocation.objects.for_company(company).filter(settlement__period_start=period_start).select_related("payment", "settlement").order_by("payment__payment_date")
        for item in qs:
            rows.append([item.payment.supplier_code, item.payment.supplier_name, item.payment.payment_number, item.payment.get_method_display(), _money(item.amount), item.payment.get_status_display(), item.payment.transaction_reference, item.payment.payment_date.isoformat()])
    paid = sum((Decimal(row[4]) for row in rows if row[5] == "Paid"), ZERO)
    return {"title": "Payments", "description": "Salary or supplier payment lifecycle records for the selected period.", "columns": ["ID", "Payee", "Payment", "Method / Channel", "Amount", "Status", "Transaction Reference", "Paid / Payment Date"], "rows": rows, "kpis": [["Rows", len(rows)], ["Paid", _money(paid)], ["Period", period_start.strftime("%B %Y")], ["Workspace", "Internal Company" if workspace == "internal" else "Rental Manpower"]], "sourceNote": "Payment history is read from payment ledgers and allocations; failed/reversed attempts remain visible."}


def _wps(company, period_start):
    profiles = EmployeePaymentProfile.objects.for_company(company).select_related("employee").order_by("employee__employee_number")
    rows = [[item.employee.employee_number, item.employee.full_name, item.get_destination_type_display(), item.bank_name, item.bank_code, "Yes" if item.wps_enabled else "No", "Configured" if (item.iban_fingerprint or item.salary_card_fingerprint) else "Missing destination"] for item in profiles]
    return {"title": "WPS / Salary Payment Setup", "description": "Employee payment-destination configuration used by the salary-payment readiness validator.", "columns": ["Employee ID", "Employee", "Destination", "Bank", "Bank Code", "WPS Enabled", "Destination Status"], "rows": rows, "kpis": [["Profiles", len(rows)], ["WPS Enabled", sum(1 for row in rows if row[5] == "Yes")], ["Configured", sum(1 for row in rows if row[6] == "Configured")], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "This is configuration visibility only. Actual export readiness remains enforced by the selected bank/WPS template at batch preparation time."}


def _workforce_cost(company, period_start):
    rows = []
    run = _run(company, period_start)
    if run and run.status in FINAL_INTERNAL:
        rows.append(["Internal Company", "Company employees", run.employee_count, "", _money(run.total_gross), _money(run.total_deductions), _money(run.total_net), run.get_status_display()])
    for item in SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL).order_by("project_name", "supplier_name"):
        rows.append(["Rental Manpower", f"{item.project_name} · {item.supplier_name}", item.worker_count, _hours(item.total_regular_hours), _money(item.total_gross + item.total_adjustment_earnings), _money(item.total_adjustment_deductions), _money(item.total_net), item.get_status_display()])
    total = sum((Decimal(row[6]) for row in rows), ZERO)
    return {"title": "Workforce Cost", "description": "Company-level comparison of finalized Internal Company and Rental Manpower cost without merging their source ledgers.", "columns": ["Workforce", "Cost Boundary", "Headcount", "Hours", "Gross / Earnings", "Deductions", "Net Cost", "Status"], "rows": rows, "kpis": [["Cost Lines", len(rows)], ["Headcount", sum(int(row[2]) for row in rows)], ["Net Cost", _money(total)], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "Internal cost uses Approved-or-later payroll snapshots; rental cost uses Approved-or-later supplier settlements only."}


def build_report(*, company, report_type: str, period_start: date, workspace: str):
    if report_type == "workforce-cost" and workspace == "management":
        return _workforce_cost(company, period_start)
    if report_type == "internal-payroll" and workspace == "internal":
        return _internal_payroll(company, period_start)
    if report_type == "rental-project-cost" and workspace == "rental":
        return _rental_group(company, period_start, by_supplier=False)
    if report_type == "supplier-cost" and workspace == "rental":
        return _rental_group(company, period_start, by_supplier=True)
    if report_type == "overtime" and workspace in {"internal", "rental", "management"}:
        return _overtime(company, period_start, workspace)
    if report_type == "advances" and workspace in {"internal", "rental"}:
        return _adjustments(company, period_start, workspace)
    if report_type == "transfers" and workspace == "rental":
        return _transfers(company, period_start)
    if report_type == "payments" and workspace in {"internal", "rental"}:
        return _payments(company, period_start, workspace)
    if report_type == "wps" and workspace == "internal":
        return _wps(company, period_start)
    raise ValueError("Unsupported report for this workspace.")
