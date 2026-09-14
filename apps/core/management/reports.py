from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum

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

# Upgrade 1.0.76: bounded interactive reporting. Full build_report() remains the
# explicit export/certification path; browser report views page at the database boundary.
REPORT_PAGE_SIZES = {25, 50, 100}


def _report_page_size(value) -> int:
    try:
        size = int(value or 50)
    except (TypeError, ValueError):
        size = 50
    return size if size in REPORT_PAGE_SIZES else 50


def _report_page_number(value) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def _page_meta(*, count: int, page: int, page_size: int) -> tuple[int, int, dict[str, int]]:
    total_pages = max(1, (count + page_size - 1) // page_size)
    page = min(max(1, page), total_pages)
    offset = (page - 1) * page_size
    end = min(count, offset + page_size)
    return page, offset, {
        "count": count,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "rangeStart": offset + 1 if count else 0,
        "rangeEnd": end,
    }


def _interactive_internal_payroll(company, period_start, *, query: str, page: int, page_size: int):
    run = _run(company, period_start)
    qs = PayrollRunLine.objects.none()
    if run:
        qs = PayrollRunLine.objects.for_company(company).filter(run=run)
        if query:
            qs = qs.filter(
                Q(employee_number__icontains=query) | Q(employee_name__icontains=query)
                | Q(branch_name__icontains=query) | Q(department_name__icontains=query)
                | Q(position__icontains=query)
            )
    qs = qs.order_by("employee_number")
    count = qs.count()
    page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = [
        [item.employee_number, item.employee_name, item.branch_name, item.department_name, item.position,
         _money(item.basic), _money(item.overtime_amount), _money(item.gross), _money(item.total_deductions), _money(item.net)]
        for item in qs[offset:offset + page_size]
    ]
    report = {
        "title": "Internal Payroll", "description": "Employee payroll snapshot by internal organization.",
        "columns": ["Employee ID", "Employee", "Branch", "Department", "Position", "Basic", "OT", "Gross", "Deductions", "Net"],
        "rows": rows,
        "kpis": [["Employees", run.employee_count if run else 0], ["Gross", _money(run.total_gross if run else 0)], ["Deductions", _money(run.total_deductions if run else 0)], ["Net", _money(run.total_net if run else 0)]],
        "sourceNote": f"Uses the stored payroll snapshot for {period_start:%B %Y}. Status: {run.get_status_display() if run else 'Not calculated'}.",
    }
    return report, meta


def _interactive_rental_group(company, period_start, *, by_supplier: bool, query: str, page: int, page_size: int):
    qs = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL)
    label_field = "supplier_name" if by_supplier else "project_name"
    id_field = "supplier_id" if by_supplier else "project_id"
    if query:
        qs = qs.filter(**{f"{label_field}__icontains": query})
    grouped = (
        qs.values(id_field, label_field)
        .annotate(
            settlements=Count("id"), workers=Sum("worker_count"), hours=Sum("total_regular_hours"),
            ot=Sum("total_overtime_hours"), gross=Sum("total_gross"), earnings=Sum("total_adjustment_earnings"),
            deductions=Sum("total_adjustment_deductions"), net=Sum("total_net"),
        )
        .order_by(label_field)
    )
    count = grouped.count()
    page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = []
    for item in grouped[offset:offset + page_size]:
        rows.append([
            item[label_field], item["settlements"], item["workers"] or 0, _hours(item["hours"]), _hours(item["ot"]),
            _money(Decimal(item["gross"] or 0) + Decimal(item["earnings"] or 0)), _money(item["deductions"]), _money(item["net"]),
        ])
    totals = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL).aggregate(
        settlements=Count("id"), workers=Sum("worker_count"), net=Sum("total_net")
    )
    report = {
        "title": "Supplier Cost" if by_supplier else "Project Manpower Cost",
        "description": "Approved rental manpower cost grouped by supplier." if by_supplier else "Approved rental manpower cost grouped by project.",
        "columns": ["Supplier" if by_supplier else "Project", "Settlements", "Workers", "Hours", "OT Hours", "Gross + Earnings", "Deductions", "Net Cost"],
        "rows": rows,
        "kpis": [["Groups", count], ["Settlements", totals["settlements"] or 0], ["Workers", totals["workers"] or 0], ["Net Cost", _money(totals["net"])]],
        "sourceNote": "Uses Approved or later supplier-settlement snapshots only; draft/review values are excluded.",
    }
    return report, meta


def _interactive_adjustments(company, period_start, workspace, *, query: str, page: int, page_size: int):
    if workspace == "internal":
        qs = PayrollAdjustment.objects.for_company(company).filter(period_start=period_start).select_related("employee")
        if query:
            qs = qs.filter(Q(employee__employee_number__icontains=query) | Q(employee__full_name__icontains=query) | Q(reference__icontains=query) | Q(reason__icontains=query))
        qs = qs.order_by("-transaction_date", "-created_at")
        row_fn = lambda item: [item.employee.employee_number, item.employee.full_name, item.get_adjustment_type_display(), item.transaction_date.isoformat(), _money(item.amount), item.get_status_display(), item.reference, item.reason]
    else:
        qs = RentalAdjustment.objects.for_company(company).filter(period_start=period_start).select_related("worker", "project", "supplier")
        if query:
            qs = qs.filter(Q(worker__worker_number__icontains=query) | Q(worker__full_name__icontains=query) | Q(reference__icontains=query) | Q(reason__icontains=query))
        qs = qs.order_by("-transaction_date", "-created_at")
        row_fn = lambda item: [item.worker.worker_number, item.worker.full_name, item.get_adjustment_type_display(), item.transaction_date.isoformat(), _money(item.amount), item.get_status_display(), item.reference, item.reason]
    count = qs.count(); page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = [row_fn(item) for item in qs[offset:offset + page_size]]
    total_qs = PayrollAdjustment.objects.for_company(company).filter(period_start=period_start) if workspace == "internal" else RentalAdjustment.objects.for_company(company).filter(period_start=period_start)
    totals = total_qs.aggregate(amount=Sum("amount"), count=Count("id"))
    report = {"title": "Advances & Adjustments", "description": "Period adjustment ledger with workflow status.", "columns": ["ID", "Person", "Type", "Date", "Amount", "Status", "Reference", "Reason"], "rows": rows, "kpis": [["Transactions", totals["count"] or 0], ["Amount", _money(totals["amount"])], ["Period", period_start.strftime("%B %Y")], ["Workspace", "Internal Company" if workspace == "internal" else "Rental Manpower"]], "sourceNote": "This report reads the transaction ledger; Approved status determines inclusion in financial calculation snapshots."}
    return report, meta


def _interactive_transfers(company, period_start, *, query: str, page: int, page_size: int):
    end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    qs = WorkerAssignment.objects.for_company(company).filter(cancelled_at__isnull=True, effective_from__range=(period_start, end)).select_related("worker", "project")
    if query:
        qs = qs.filter(Q(worker__worker_number__icontains=query) | Q(worker__full_name__icontains=query) | Q(project__code__icontains=query) | Q(project__name__icontains=query) | Q(trade__icontains=query) | Q(reason__icontains=query))
    qs = qs.order_by("-effective_from", "worker__worker_number")
    count = qs.count(); page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = [[item.worker.worker_number, item.worker.full_name, item.project.code, item.project.name, item.get_change_type_display(), item.trade, item.get_rate_type_display(), str(item.rate), item.effective_from.isoformat(), item.effective_to.isoformat() if item.effective_to else ""] for item in qs[offset:offset + page_size]]
    base = WorkerAssignment.objects.for_company(company).filter(cancelled_at__isnull=True, effective_from__range=(period_start, end))
    report = {"title": "Worker Transfers & Assignment Changes", "description": "Effective-dated rental assignment lifecycle changes.", "columns": ["Worker ID", "Worker", "Project Code", "Project", "Change", "Trade", "Rate Type", "Rate", "Effective From", "Effective To"], "rows": rows, "kpis": [["Changes", base.count()], ["Period", period_start.strftime("%B %Y")], ["Transfers", base.filter(change_type="transfer").count()], ["Rate Changes", base.filter(change_type="rate_change").count()]], "sourceNote": "Reads immutable/effective-dated assignment segments; cancelled scheduled changes are excluded."}
    return report, meta


def _interactive_payments(company, period_start, workspace, *, query: str, page: int, page_size: int):
    if workspace == "internal":
        qs = SalaryPaymentRow.objects.for_company(company).filter(batch__run__period_start=period_start).select_related("batch")
        if query:
            qs = qs.filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(batch__reference__icontains=query) | Q(transaction_reference__icontains=query))
        qs = qs.order_by("employee_number", "-batch__prepared_at")
        row_fn = lambda item: [item.employee_number, item.employee_name, item.batch.reference, item.batch.get_channel_display(), _money(item.amount), item.get_status_display(), item.transaction_reference, item.paid_at.isoformat() if item.paid_at else ""]
        total_qs = SalaryPaymentRow.objects.for_company(company).filter(batch__run__period_start=period_start)
        paid = total_qs.filter(status="paid").aggregate(total=Sum("amount"))["total"] or ZERO
        total_count = total_qs.count()
    else:
        qs = SupplierPaymentAllocation.objects.for_company(company).filter(settlement__period_start=period_start).select_related("payment", "settlement")
        if query:
            qs = qs.filter(Q(payment__supplier_code__icontains=query) | Q(payment__supplier_name__icontains=query) | Q(payment__payment_number__icontains=query) | Q(payment__transaction_reference__icontains=query))
        qs = qs.order_by("-payment__payment_date", "payment__payment_number")
        row_fn = lambda item: [item.payment.supplier_code, item.payment.supplier_name, item.payment.payment_number, item.payment.get_method_display(), _money(item.amount), item.payment.get_status_display(), item.payment.transaction_reference, item.payment.payment_date.isoformat()]
        total_qs = SupplierPaymentAllocation.objects.for_company(company).filter(settlement__period_start=period_start)
        paid = total_qs.filter(payment__status="paid").aggregate(total=Sum("amount"))["total"] or ZERO
        total_count = total_qs.count()
    count = qs.count(); page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = [row_fn(item) for item in qs[offset:offset + page_size]]
    report = {"title": "Payments", "description": "Salary or supplier payment lifecycle records for the selected period.", "columns": ["ID", "Payee", "Payment", "Method / Channel", "Amount", "Status", "Transaction Reference", "Paid / Payment Date"], "rows": rows, "kpis": [["Rows", total_count], ["Paid", _money(paid)], ["Period", period_start.strftime("%B %Y")], ["Workspace", "Internal Company" if workspace == "internal" else "Rental Manpower"]], "sourceNote": "Payment history is read from payment ledgers and allocations; failed/reversed attempts remain visible."}
    return report, meta


def _interactive_wps(company, period_start, *, query: str, page: int, page_size: int):
    qs = EmployeePaymentProfile.objects.for_company(company).select_related("employee")
    if query:
        qs = qs.filter(Q(employee__employee_number__icontains=query) | Q(employee__full_name__icontains=query) | Q(bank_name__icontains=query) | Q(bank_code__icontains=query))
    qs = qs.order_by("employee__employee_number")
    count = qs.count(); page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = [[item.employee.employee_number, item.employee.full_name, item.get_destination_type_display(), item.bank_name, item.bank_code, "Yes" if item.wps_enabled else "No", "Configured" if (item.iban_fingerprint or item.salary_card_fingerprint) else "Missing destination"] for item in qs[offset:offset + page_size]]
    base = EmployeePaymentProfile.objects.for_company(company)
    report = {"title": "WPS / Salary Payment Setup", "description": "Employee payment-destination configuration used by the salary-payment readiness validator.", "columns": ["Employee ID", "Employee", "Destination", "Bank", "Bank Code", "WPS Enabled", "Destination Status"], "rows": rows, "kpis": [["Profiles", base.count()], ["WPS Enabled", base.filter(wps_enabled=True).count()], ["Configured", base.filter(Q(iban_fingerprint__gt="") | Q(salary_card_fingerprint__gt="")).count()], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "This is configuration visibility only. Actual export readiness remains enforced by the selected bank/WPS template at batch preparation time."}
    return report, meta


def _interactive_overtime(company, period_start, workspace, *, query: str, page: int, page_size: int):
    run = _run(company, period_start) if workspace in {"internal", "management"} else None
    internal = PayrollRunLine.objects.none()
    if run:
        internal = PayrollRunLine.objects.for_company(company).filter(run=run, overtime_hours__gt=0)
        if query:
            internal = internal.filter(Q(employee_number__icontains=query) | Q(employee_name__icontains=query) | Q(branch_name__icontains=query))
        internal = internal.order_by("employee_number")
    rental = SupplierSettlementLine.objects.none()
    if workspace in {"rental", "management"}:
        rental = SupplierSettlementLine.objects.for_company(company).filter(settlement__period_start=period_start, settlement__status__in=FINAL_RENTAL, overtime_hours__gt=0).select_related("settlement")
        if query:
            rental = rental.filter(Q(worker_number__icontains=query) | Q(worker_name__icontains=query) | Q(settlement__project_name__icontains=query))
        rental = rental.order_by("worker_number")
    internal_count = internal.count(); rental_count = rental.count(); count = internal_count + rental_count
    page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = []
    internal_take_start = min(offset, internal_count)
    internal_take_end = min(internal_count, offset + page_size)
    if internal_take_end > internal_take_start:
        rows.extend([["Internal", item.employee_number, item.employee_name, item.branch_name, _hours(item.overtime_hours), str(item.overtime_rate or ""), _money(item.overtime_amount)] for item in internal[internal_take_start:internal_take_end]])
    remaining = page_size - len(rows)
    rental_offset = max(0, offset - internal_count)
    if remaining > 0:
        rows.extend([["Rental", item.worker_number, item.worker_name, item.settlement.project_name, _hours(item.overtime_hours), "Snapshot", _money(item.overtime_amount)] for item in rental[rental_offset:rental_offset + remaining]])
    int_totals = (PayrollRunLine.objects.for_company(company).filter(run=run, overtime_hours__gt=0).aggregate(hours=Sum("overtime_hours"), amount=Sum("overtime_amount"), count=Count("id")) if run and workspace in {"internal", "management"} else {"hours": ZERO, "amount": ZERO, "count": 0})
    rent_totals = (SupplierSettlementLine.objects.for_company(company).filter(settlement__period_start=period_start, settlement__status__in=FINAL_RENTAL, overtime_hours__gt=0).aggregate(hours=Sum("overtime_hours"), amount=Sum("overtime_amount"), count=Count("id")) if workspace in {"rental", "management"} else {"hours": ZERO, "amount": ZERO, "count": 0})
    report = {"title": "Overtime", "description": "Overtime captured in controlled payroll/settlement snapshots.", "columns": ["Workforce", "ID", "Name", "Branch / Project", "OT Hours", "Rate", "OT Amount"], "rows": rows, "kpis": [["Records", int(int_totals["count"] or 0) + int(rent_totals["count"] or 0)], ["OT Hours", _hours(Decimal(int_totals["hours"] or 0) + Decimal(rent_totals["hours"] or 0))], ["OT Amount", _money(Decimal(int_totals["amount"] or 0) + Decimal(rent_totals["amount"] or 0))], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "Internal values come from payroll snapshots; rental values come from approved supplier-settlement snapshots."}
    return report, meta


def _interactive_workforce_cost(company, period_start, *, query: str, page: int, page_size: int):
    run = _run(company, period_start)
    internal_row = None
    if run and run.status in FINAL_INTERNAL:
        internal_row = ["Internal Company", "Company employees", run.employee_count, "", _money(run.total_gross), _money(run.total_deductions), _money(run.total_net), run.get_status_display()]
        if query and query.casefold() not in " ".join(str(value) for value in internal_row).casefold():
            internal_row = None
    rental = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL)
    if query:
        rental = rental.filter(Q(project_name__icontains=query) | Q(supplier_name__icontains=query) | Q(settlement_number__icontains=query))
    rental = rental.order_by("project_name", "supplier_name")
    count = rental.count() + (1 if internal_row else 0)
    page, offset, meta = _page_meta(count=count, page=page, page_size=page_size)
    rows = []
    if internal_row and offset == 0:
        rows.append(internal_row)
    rental_offset = max(0, offset - (1 if internal_row else 0))
    remaining = page_size - len(rows)
    if remaining:
        rows.extend([["Rental Manpower", f"{item.project_name} · {item.supplier_name}", item.worker_count, _hours(item.total_regular_hours), _money(item.total_gross + item.total_adjustment_earnings), _money(item.total_adjustment_deductions), _money(item.total_net), item.get_status_display()] for item in rental[rental_offset:rental_offset + remaining]])
    all_rental = SupplierSettlement.objects.for_company(company).filter(period_start=period_start, status__in=FINAL_RENTAL).aggregate(headcount=Sum("worker_count"), net=Sum("total_net"), count=Count("id"))
    headcount = int(all_rental["headcount"] or 0) + (int(run.employee_count) if run and run.status in FINAL_INTERNAL else 0)
    net = Decimal(all_rental["net"] or 0) + (Decimal(run.total_net) if run and run.status in FINAL_INTERNAL else ZERO)
    report = {"title": "Workforce Cost", "description": "Company-level comparison of finalized Internal Company and Rental Manpower cost without merging their source ledgers.", "columns": ["Workforce", "Cost Boundary", "Headcount", "Hours", "Gross / Earnings", "Deductions", "Net Cost", "Status"], "rows": rows, "kpis": [["Cost Lines", int(all_rental["count"] or 0) + (1 if run and run.status in FINAL_INTERNAL else 0)], ["Headcount", headcount], ["Net Cost", _money(net)], ["Period", period_start.strftime("%B %Y")]], "sourceNote": "Internal cost uses Approved-or-later payroll snapshots; rental cost uses Approved-or-later supplier settlements only."}
    return report, meta


def build_report_page(*, company, report_type: str, period_start: date, workspace: str, query: str = "", page: object = 1, page_size: object = 50):
    size = _report_page_size(page_size); number = _report_page_number(page); q = str(query or "").strip()
    if report_type == "workforce-cost" and workspace == "management": result = _interactive_workforce_cost(company, period_start, query=q, page=number, page_size=size)
    elif report_type == "internal-payroll" and workspace == "internal": result = _interactive_internal_payroll(company, period_start, query=q, page=number, page_size=size)
    elif report_type == "rental-project-cost" and workspace == "rental": result = _interactive_rental_group(company, period_start, by_supplier=False, query=q, page=number, page_size=size)
    elif report_type == "supplier-cost" and workspace == "rental": result = _interactive_rental_group(company, period_start, by_supplier=True, query=q, page=number, page_size=size)
    elif report_type == "overtime" and workspace in {"internal", "rental", "management"}: result = _interactive_overtime(company, period_start, workspace, query=q, page=number, page_size=size)
    elif report_type == "advances" and workspace in {"internal", "rental"}: result = _interactive_adjustments(company, period_start, workspace, query=q, page=number, page_size=size)
    elif report_type == "transfers" and workspace == "rental": result = _interactive_transfers(company, period_start, query=q, page=number, page_size=size)
    elif report_type == "payments" and workspace in {"internal", "rental"}: result = _interactive_payments(company, period_start, workspace, query=q, page=number, page_size=size)
    elif report_type == "wps" and workspace == "internal": result = _interactive_wps(company, period_start, query=q, page=number, page_size=size)
    else: raise ValueError("Unsupported report for this workspace.")
    report, meta = result
    report["meta"] = meta
    return report
