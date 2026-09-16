from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, DecimalField, F, Max, Prefetch, Q, Sum
from django.db.models.functions import Coalesce

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.core.models import AuditArea, AuditEvent, Company
from apps.internal_payroll.models import (
    AttendancePeriodStatus,
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
    employee = getattr(adjustment, "employee", None)
    employee_number = getattr(employee, "employee_number", "") if employee is not None else ""
    employee_name = getattr(employee, "full_name", "") if employee is not None else ""
    return {
        "id": str(adjustment.pk),
        "employeeId": str(adjustment.employee_id),
        "personId": str(adjustment.employee_id),
        "personName": employee_name,
        "personCode": f"EMP {employee_number}" if employee_number else "",
        "workforce": "Internal Employee",
        "workforceKey": "Internal",
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
        "projectId": None,
        "project": "Employee-level",
        "supplierId": None,
        "supplier": "—",
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


ADJUSTMENT_PAGE_SIZES = {25, 50, 100}


def _adjustment_page_size(value: object) -> int:
    try:
        page_size = int(value)
    except (TypeError, ValueError):
        page_size = 50
    if page_size not in ADJUSTMENT_PAGE_SIZES:
        raise ValidationError({"page_size": "Adjustment page size must be 25, 50, or 100."})
    return page_size


def _adjustment_page_number(value: object) -> int:
    try:
        page = int(value)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        raise ValidationError({"page": "Adjustment page must be at least 1."})
    return page


def _choice_value(raw: str, choices, field: str) -> str | None:
    value = str(raw or "").strip()
    if not value or value.lower() == "all":
        return None
    normalized = value.lower().replace(" ", "_").replace("/", "_")
    for choice_value, choice_label in choices:
        if value == choice_value or value.lower() == str(choice_label).lower() or normalized == choice_value:
            return choice_value
    raise ValidationError({field: f"Unknown {field} filter."})


def _adjustment_period_summary(*, company: Company, period_start: date) -> dict[str, object]:
    start, _end = month_bounds(period_start)
    rows = PayrollAdjustment.objects.for_company(company).filter(period_start=start)
    approved = rows.filter(status=PayrollAdjustmentStatus.APPROVED)
    earnings = approved.filter(
        adjustment_type__in=[
            PayrollAdjustmentType.BONUS, PayrollAdjustmentType.REIMBURSEMENT, PayrollAdjustmentType.OTHER_EARNING
        ]
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    deductions = approved.filter(
        adjustment_type__in=[
            PayrollAdjustmentType.ADVANCE_RECOVERY, PayrollAdjustmentType.FINE, PayrollAdjustmentType.OTHER_DEDUCTION
        ]
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    advance_issues = approved.filter(adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "count": rows.count(),
        "earnings": str(earnings),
        "deductions": str(deductions),
        "advanceIssues": str(advance_issues),
        "pending": rows.exclude(status=PayrollAdjustmentStatus.APPROVED).count(),
    }


def _advance_balance_queryset(*, company: Company, query: str = ""):
    money = DecimalField(max_digits=18, decimal_places=2)
    rows = (
        PayrollAdjustment.objects.for_company(company)
        .filter(
            status=PayrollAdjustmentStatus.APPROVED,
            adjustment_type__in=[PayrollAdjustmentType.SALARY_ADVANCE, PayrollAdjustmentType.ADVANCE_RECOVERY],
        )
        .values("employee_id", "employee__employee_number", "employee__full_name")
        .annotate(
            issued=Coalesce(
                Sum("amount", filter=Q(adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE)),
                Decimal("0"), output_field=money,
            ),
            recovered=Coalesce(
                Sum("amount", filter=Q(adjustment_type=PayrollAdjustmentType.ADVANCE_RECOVERY)),
                Decimal("0"), output_field=money,
            ),
            last_date=Max("transaction_date"),
        )
        .annotate(balance=F("issued") - F("recovered"))
        .filter(balance__gt=0)
    )
    query = query.strip()
    if query:
        rows = rows.filter(
            Q(employee__full_name__icontains=query)
            | Q(employee__employee_number__icontains=query)
        )
    return rows.order_by("-balance", "employee__full_name", "employee_id")


def _advance_balance_summary(*, company: Company) -> dict[str, object]:
    rows = PayrollAdjustment.objects.for_company(company).filter(
        status=PayrollAdjustmentStatus.APPROVED,
        adjustment_type__in=[PayrollAdjustmentType.SALARY_ADVANCE, PayrollAdjustmentType.ADVANCE_RECOVERY],
    )
    issued = rows.filter(adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    recovered = rows.filter(adjustment_type=PayrollAdjustmentType.ADVANCE_RECOVERY).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    return {
        "outstanding": str(max(Decimal("0"), issued - recovered)),
        "activeCount": _advance_balance_queryset(company=company).count(),
    }


def payroll_adjustment_page_context(
    *, company: Company, period_start: date, page: object = 1, page_size: object = 50,
    search: str = "", adjustment_type: str = "All", status: str = "All", view: str = "register",
) -> dict[str, object]:
    start, _end = month_bounds(period_start)
    page_number = _adjustment_page_number(page)
    size = _adjustment_page_size(page_size)
    normalized_view = str(view or "register").strip().lower()
    if normalized_view not in {"register", "balances"}:
        raise ValidationError({"view": "Adjustment view must be register or balances."})
    summary = _adjustment_period_summary(company=company, period_start=start)
    balance_summary = _advance_balance_summary(company=company)

    if normalized_view == "balances":
        queryset = _advance_balance_queryset(company=company, query=search)
        paginator = Paginator(queryset, size)
        page_obj = paginator.get_page(page_number)
        raw_rows = list(page_obj.object_list)
        employee_ids = [row["employee_id"] for row in raw_rows]
        pending = {
            str(row["employee_id"]): row["total"] or Decimal("0")
            for row in (
                PayrollAdjustment.objects.for_company(company)
                .filter(
                    employee_id__in=employee_ids,
                    adjustment_type__in=[PayrollAdjustmentType.SALARY_ADVANCE, PayrollAdjustmentType.ADVANCE_RECOVERY],
                )
                .exclude(status=PayrollAdjustmentStatus.APPROVED)
                .values("employee_id")
                .annotate(total=Sum("amount"))
            )
        }
        latest_plans: dict[str, PayrollAdjustment] = {}
        if employee_ids:
            for item in (
                PayrollAdjustment.objects.for_company(company)
                .filter(
                    employee_id__in=employee_ids,
                    status=PayrollAdjustmentStatus.APPROVED,
                    adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE,
                )
                .order_by("employee_id", "-transaction_date", "-created_at")
                .distinct("employee_id")
            ):
                latest_plans[str(item.employee_id)] = item
        results = []
        for row in raw_rows:
            employee_id = str(row["employee_id"])
            plan = latest_plans.get(employee_id)
            results.append({
                "key": f"Internal:{employee_id}",
                "workforce": "Internal Employee",
                "workforceKey": "Internal",
                "personId": employee_id,
                "personName": row["employee__full_name"],
                "personCode": f"EMP {row['employee__employee_number']}",
                "issued": str(row["issued"]),
                "recovered": str(row["recovered"]),
                "balance": str(row["balance"]),
                "pending": str(pending.get(employee_id, Decimal("0"))),
                "lastDate": row["last_date"].isoformat() if row["last_date"] else "",
                "plans": ([{
                    "plan": plan.recovery_plan or "Manual recovery",
                    "installment": str(plan.installment_amount or ""),
                    "start": plan.recovery_start.isoformat() if plan.recovery_start else "",
                }] if plan else []),
            })
        return {
            "surface": "adjustments_page", "period": f"{start:%Y-%m}", "view": "balances",
            "results": [], "balances": results, "summary": summary, "balanceSummary": balance_summary,
            "meta": {
                "count": paginator.count, "page": page_obj.number, "pageSize": size,
                "totalPages": paginator.num_pages,
                "rangeStart": (page_obj.start_index() if paginator.count else 0),
                "rangeEnd": (page_obj.end_index() if paginator.count else 0),
            },
            "filters": {
                "types": [{"value": value, "label": label} for value, label in PayrollAdjustmentType.choices],
                "statuses": [{"value": value, "label": label} for value, label in PayrollAdjustmentStatus.choices],
            },
        }

    type_value = _choice_value(adjustment_type, PayrollAdjustmentType.choices, "type")
    status_value = _choice_value(status, PayrollAdjustmentStatus.choices, "status")
    queryset = (
        PayrollAdjustment.objects.for_company(company)
        .filter(period_start=start)
        .select_related("employee", "submitted_by", "approved_by")
    )
    query = search.strip()
    if query:
        normalized_query = query.lower().replace(" ", "_")
        queryset = queryset.filter(
            Q(employee__full_name__icontains=query)
            | Q(employee__employee_number__icontains=query)
            | Q(reason__icontains=query)
            | Q(reference__icontains=query)
            | Q(adjustment_type__icontains=normalized_query)
        )
    if type_value:
        queryset = queryset.filter(adjustment_type=type_value)
    if status_value:
        queryset = queryset.filter(status=status_value)
    queryset = queryset.order_by("-transaction_date", "-created_at", "-pk")
    paginator = Paginator(queryset, size)
    page_obj = paginator.get_page(page_number)
    return {
        "surface": "adjustments_page", "period": f"{start:%Y-%m}", "view": "register",
        "results": [serialize_payroll_adjustment(item) for item in page_obj.object_list],
        "balances": [], "summary": summary, "balanceSummary": balance_summary,
        "meta": {
            "count": paginator.count, "page": page_obj.number, "pageSize": size,
            "totalPages": paginator.num_pages,
            "rangeStart": (page_obj.start_index() if paginator.count else 0),
            "rangeEnd": (page_obj.end_index() if paginator.count else 0),
        },
        "filters": {
            "types": [{"value": value, "label": label} for value, label in PayrollAdjustmentType.choices],
            "statuses": [{"value": value, "label": label} for value, label in PayrollAdjustmentStatus.choices],
        },
    }


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
        .select_related("attendance_period", "calculated_by", "submitted_by", "reviewed_by", "approved_by")
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
        "internal.payroll_run.reviewed": "Finance review signed off",
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
    can_prepare = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE))
    can_review = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW))
    can_approve = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE))
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
        "reviewedAt": run.reviewed_at.isoformat() if run and run.reviewed_at else None,
        "reviewedBy": _user_label(run.reviewed_by) if run else None,
        "approvedAt": run.approved_at.isoformat() if run and run.approved_at else None,
        "approvedBy": _user_label(run.approved_by) if run else None,
        "reviewerNote": run.reviewer_note if run else "",
        "canEdit": can_prepare,
        "canPrepare": can_prepare,
        "canReview": can_review,
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




PAYROLL_RUN_PAGE_SIZES = {25, 50, 100}


def _page_int(value: object, default: int = 1) -> int:
    try:
        parsed = int(str(value or default))
    except (TypeError, ValueError):
        parsed = default
    return max(1, parsed)


def _payroll_page_size(value: object) -> int:
    parsed = _page_int(value, 50)
    return parsed if parsed in PAYROLL_RUN_PAGE_SIZES else 50


def _run_header_for_period(*, company: Company, period_start: date) -> PayrollRun | None:
    start, _end = month_bounds(period_start)
    return (
        PayrollRun.objects.for_company(company)
        .select_related("attendance_period", "calculated_by", "submitted_by", "reviewed_by", "approved_by")
        .filter(period_start=start)
        .first()
    )


def _snapshot_lines_queryset(*, company: Company, run: PayrollRun):
    return PayrollRunLine.objects.for_company(company).filter(run=run).select_related("employee").order_by("employee_number", "employee_name")


def _page_snapshot_lines(queryset, *, company: Company, offset: int, page_size: int) -> list[PayrollRunLine]:
    components = PayrollRunLineComponent.objects.for_company(company).order_by("component_category", "component_code", "effective_from")
    adjustments = PayrollRunLineAdjustment.objects.for_company(company).order_by("transaction_date", "created_at")
    return list(
        queryset[offset : offset + page_size].prefetch_related(
            Prefetch("components", queryset=components, to_attr="payroll_components"),
            Prefetch("adjustments", queryset=adjustments, to_attr="payroll_adjustments"),
        )
    )


def _row_total_summary(rows: list[dict[str, object]]) -> dict[str, object]:
    totals = {
        "employeeCount": len(rows),
        "basic": Decimal("0"), "allowances": Decimal("0"), "overtime": Decimal("0"),
        "otherEarnings": Decimal("0"), "gross": Decimal("0"), "advanceRecovery": Decimal("0"),
        "otherDeductions": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0"),
        "ready": 0, "blocked": 0, "warning": 0,
    }
    for row in rows:
        totals["basic"] += Decimal(str(row.get("basic") or 0))
        totals["allowances"] += Decimal(str(row.get("allowances") or 0))
        totals["overtime"] += Decimal(str(row.get("overtime") or 0))
        totals["otherEarnings"] += Decimal(str(row.get("otherEarnings") or 0))
        totals["gross"] += Decimal(str(row.get("gross") or 0))
        totals["advanceRecovery"] += Decimal(str(row.get("advances") or 0))
        totals["otherDeductions"] += Decimal(str(row.get("deductions") or 0))
        totals["deductions"] += Decimal(str(row.get("advances") or 0)) + Decimal(str(row.get("deductions") or 0))
        totals["net"] += Decimal(str(row.get("net") or 0))
        if row.get("blockers"):
            totals["blocked"] += 1
        else:
            totals["ready"] += 1
        if row.get("warnings"):
            totals["warning"] += 1
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in totals.items()}


def _run_total_summary(run: PayrollRun) -> dict[str, object]:
    return {
        "employeeCount": run.employee_count,
        "basic": str(run.total_basic), "allowances": str(run.total_allowances), "overtime": str(run.total_overtime),
        "otherEarnings": str(run.total_other_earnings), "gross": str(run.total_gross),
        "advanceRecovery": str(run.total_advance_recovery), "otherDeductions": str(run.total_other_deductions),
        "deductions": str(run.total_deductions), "net": str(run.total_net),
        "ready": run.employee_count, "blocked": 0, "warning": 0,
    }


def _filter_preview_rows(rows: list[dict[str, object]], *, search: str, branch: str, department: str, readiness: str) -> list[dict[str, object]]:
    needle = search.casefold().strip()
    result: list[dict[str, object]] = []
    for row in rows:
        if branch and branch != "All branches" and str(row.get("branch") or "") != branch:
            continue
        if department and department != "All departments" and str(row.get("department") or "") != department:
            continue
        blocked = bool(row.get("blockers"))
        if readiness == "Blocked" and not blocked:
            continue
        if readiness == "Ready" and blocked:
            continue
        if needle:
            haystack = " ".join(str(row.get(key) or "") for key in ("employeeCode", "name", "position", "department", "branch")).casefold()
            if needle not in haystack:
                continue
        result.append(row)
    return result


def _snapshot_filter(queryset, *, search: str, branch: str, department: str, readiness: str):
    if search.strip():
        needle = search.strip()
        queryset = queryset.filter(
            Q(employee_number__icontains=needle)
            | Q(employee_name__icontains=needle)
            | Q(position__icontains=needle)
            | Q(department_name__icontains=needle)
            | Q(branch_name__icontains=needle)
        )
    if branch and branch != "All branches":
        queryset = queryset.filter(branch_name=branch)
    if department and department != "All departments":
        queryset = queryset.filter(department_name=department)
    # Persisted payroll snapshots are created only after all source blockers are clear.
    if readiness == "Blocked":
        queryset = queryset.none()
    return queryset


def _comparison_rows(*, company: Company, previous_run: PayrollRun | None, employee_ids: list[str]) -> list[dict[str, object]]:
    if previous_run is None or not employee_ids:
        return []
    return [
        {
            "employeeId": str(item["employee_id"]),
            "employeeCode": item["employee_number"],
            "name": item["employee_name"],
            "net": str(item["net"]),
        }
        for item in PayrollRunLine.objects.for_company(company)
        .filter(run=previous_run, employee_id__in=employee_ids)
        .values("employee_id", "employee_number", "employee_name", "net")
    ]


def _review_summary(*, rows: list[dict[str, object]], previous_net_by_employee: dict[str, Decimal], source_errors: list[str], attendance_locked: bool, previous_available: bool) -> dict[str, int]:
    critical = len(source_errors) + (0 if attendance_locked else 1)
    warning = 0
    for row in rows:
        critical += len(row.get("blockers") or [])
        warning += len(row.get("warnings") or [])
        basic = Decimal(str(row.get("basic") or 0))
        overtime = Decimal(str(row.get("overtime") or 0))
        overtime_hours = Decimal(str(row.get("otHours") or 0))
        if overtime_hours >= 40 or (basic > 0 and overtime / basic >= Decimal("0.2")):
            warning += 1
        previous = previous_net_by_employee.get(str(row.get("employeeId")))
        current = Decimal(str(row.get("net") or 0))
        if previous not in (None, Decimal("0")):
            delta_pct = abs((current - previous) / previous * Decimal("100"))
            if delta_pct >= 25:
                critical += 1
            elif delta_pct >= 10:
                warning += 1
    info = 0 if previous_available else 1
    return {"Critical": critical, "Warning": warning, "Info": info, "All": critical + warning + info}


def payroll_run_page_context(
    *,
    company: Company,
    period_start: date,
    membership=None,
    page: object = 1,
    page_size: object = 50,
    search: str = "",
    branch: str = "All branches",
    department: str = "All departments",
    readiness: str = "All",
) -> dict[str, object]:
    """Bounded Payroll Runs surface.

    Saved runs page directly from immutable PayrollRunLine rows. Draft remains an
    authoritative server preflight, but only the requested page crosses the API boundary.
    """
    start, _end = month_bounds(period_start)
    page_number = _page_int(page)
    size = _payroll_page_size(page_size)
    run = _run_header_for_period(company=company, period_start=start)
    policy = payroll_policy_for_company(company=company)
    source_errors: list[str] = []

    if run is not None and run.status != PayrollRunStatus.DRAFT:
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
        base_queryset = _snapshot_lines_queryset(company=company, run=run)
        branches = list(base_queryset.exclude(branch_name="").values_list("branch_name", flat=True).distinct().order_by("branch_name"))
        departments = list(base_queryset.exclude(department_name="").values_list("department_name", flat=True).distinct().order_by("department_name"))
        filtered_queryset = _snapshot_filter(base_queryset, search=search, branch=branch, department=department, readiness=readiness)
        count = filtered_queryset.count()
        total_pages = max(1, (count + size - 1) // size)
        page_number = min(page_number, total_pages)
        offset = (page_number - 1) * size
        rows = [_serialize_snapshot_line(item) for item in _page_snapshot_lines(filtered_queryset, company=company, offset=offset, page_size=size)]
        summary = _run_total_summary(run)
        # Warnings are not financial blockers; count employees with non-approved period adjustments exactly.
        pending_warning_count = (
            PayrollAdjustment.objects.for_company(company)
            .filter(period_start=start)
            .exclude(status=PayrollAdjustmentStatus.APPROVED)
            .values("employee_id")
            .distinct()
            .count()
        )
        summary["warning"] = pending_warning_count
        all_review_rows = [
            {
                "employeeId": str(item["employee_id"]), "basic": str(item["basic"]), "overtime": str(item["overtime_amount"]),
                "otHours": str(item["overtime_hours"]), "net": str(item["net"]), "blockers": [], "warnings": [],
            }
            for item in base_queryset.values("employee_id", "basic", "overtime_amount", "overtime_hours", "net")
        ]
    else:
        try:
            preview = preview_payroll_run(company=company, period_start=start)
            all_review_rows = list(preview["rows"])
            source_errors = list(preview["blockers"])
        except ValidationError as exc:
            all_review_rows = []
            if hasattr(exc, "message_dict"):
                source_errors = [str(message) for messages in exc.message_dict.values() for message in messages]
            else:
                source_errors = [str(message) for message in exc.messages]
        branches = sorted({str(row.get("branch") or "") for row in all_review_rows if row.get("branch")})
        departments = sorted({str(row.get("department") or "") for row in all_review_rows if row.get("department")})
        summary = _row_total_summary(all_review_rows)
        filtered = _filter_preview_rows(all_review_rows, search=search, branch=branch, department=department, readiness=readiness)
        count = len(filtered)
        total_pages = max(1, (count + size - 1) // size)
        page_number = min(page_number, total_pages)
        offset = (page_number - 1) * size
        rows = filtered[offset : offset + size]

    if run is None or run.status == PayrollRunStatus.DRAFT:
        pending_warning_count = (
            PayrollAdjustment.objects.for_company(company)
            .filter(period_start=start)
            .exclude(status=PayrollAdjustmentStatus.APPROVED)
            .values("employee_id")
            .distinct()
            .count()
        )
        summary["warning"] = pending_warning_count

    # Add only visible employees' pending adjustments; 1.0.74 will cut over the full adjustments workspace.
    visible_employee_ids = [str(row.get("employeeId")) for row in rows if row.get("employeeId")]
    adjustments_by_employee: dict[str, list[dict[str, object]]] = {}
    if visible_employee_ids:
        page_adjustments = list(
            PayrollAdjustment.objects.for_company(company)
            .filter(period_start=start, employee_id__in=visible_employee_ids)
            .select_related("employee", "submitted_by", "approved_by")
            .order_by("-transaction_date", "-created_at")
        )
        for item in page_adjustments:
            adjustments_by_employee.setdefault(str(item.employee_id), []).append(serialize_payroll_adjustment(item))
        for row in rows:
            pending = [item for item in adjustments_by_employee.get(str(row.get("employeeId")), []) if item.get("statusValue") != PayrollAdjustmentStatus.APPROVED]
            row["pendingAdjustments"] = pending
            if pending:
                row.setdefault("warnings", []).append(f"{len(pending)} adjustment(s) are not approved and are excluded from payroll.")

    previous_start = _previous_period(start)
    previous_run = _run_header_for_period(company=company, period_start=previous_start)
    previous_rows = _comparison_rows(company=company, previous_run=previous_run, employee_ids=visible_employee_ids)
    previous_net_by_employee = {
        str(item["employee_id"]): Decimal(str(item["net"]))
        for item in PayrollRunLine.objects.for_company(company)
        .filter(run=previous_run)
        .values("employee_id", "net")
    } if previous_run else {}

    attendance_status = None
    if run and run.attendance_period:
        attendance_status = run.attendance_period.get_status_display()
    else:
        from apps.internal_payroll.selectors.attendance import attendance_period_for_company
        attendance = attendance_period_for_company(company=company, period_start=start)
        attendance_status = attendance.get_status_display() if attendance else "Not created"
    attendance_calculable = attendance_status in {AttendancePeriodStatus.APPROVED.label, AttendancePeriodStatus.LOCKED.label}
    attendance_locked = attendance_status == AttendancePeriodStatus.LOCKED.label
    run_status = run.status if run else PayrollRunStatus.DRAFT
    can_prepare = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE))
    can_review = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW))
    can_approve = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE))
    source_clear = not source_errors and int(summary.get("blocked") or 0) == 0
    review_signed_off = bool(run and run.reviewed_at and run.reviewed_by_id)
    allowed_actions: list[str] = []
    if can_prepare and run_status in {PayrollRunStatus.DRAFT, PayrollRunStatus.CALCULATED} and attendance_calculable and source_clear:
        allowed_actions.append("calculate")
    if can_prepare and run_status == PayrollRunStatus.CALCULATED:
        allowed_actions.append("reset")
        if attendance_locked and source_clear:
            allowed_actions.append("submit_review")
    if can_review and run_status == PayrollRunStatus.REVIEW:
        allowed_actions.append("return_for_changes")
        if attendance_locked and source_clear and not review_signed_off:
            allowed_actions.append("review")
    if can_approve and run_status == PayrollRunStatus.REVIEW and review_signed_off and attendance_locked and source_clear:
        allowed_actions.append("approve")
    next_action = next((item for item in ("calculate", "submit_review", "review", "approve") if item in allowed_actions), None)

    review_summary = _review_summary(
        rows=all_review_rows,
        previous_net_by_employee=previous_net_by_employee,
        source_errors=source_errors,
        attendance_locked=attendance_locked,
        previous_available=previous_run is not None and previous_run.employee_count > 0,
    )
    if pending_warning_count:
        review_summary["Warning"] += pending_warning_count
        review_summary["All"] += pending_warning_count
    return {
        "surface": "payroll_run_page",
        "run": _run_payload(run, period_start=start, membership=membership),
        "rows": rows,
        "summary": summary,
        "meta": {
            "page": page_number, "pageSize": size, "count": count, "totalPages": total_pages,
            "rangeStart": 0 if count == 0 else offset + 1, "rangeEnd": min(offset + size, count),
        },
        "filters": {"branches": branches, "departments": departments},
        "sourceErrors": source_errors,
        "policy": serialize_payroll_policy(policy),
        "adjustments": [],
        "adjustmentsByEmployee": adjustments_by_employee,
        "reviewSummary": review_summary,
        "reviewHistory": _audit_history(run),
        "attendanceStatus": attendance_status,
        "attendanceLocked": attendance_locked,
        "workflow": {
            "statusValue": run_status, "allowedActions": allowed_actions, "nextAction": next_action,
            "canCalculate": "calculate" in allowed_actions, "canReset": "reset" in allowed_actions,
            "canSubmitReview": "submit_review" in allowed_actions, "canReview": "review" in allowed_actions,
            "reviewSignedOff": review_signed_off, "canReturnForChanges": "return_for_changes" in allowed_actions,
            "canApprove": "approve" in allowed_actions, "sourceClear": source_clear,
            "attendanceCalculable": attendance_calculable, "attendanceLocked": attendance_locked,
        },
        "previous": {
            "period": f"{previous_start:%Y-%m}", "label": _period_label(previous_start),
            "run": _run_payload(previous_run, period_start=previous_start, membership=membership) if previous_run else None,
            "rows": previous_rows,
        },
    }


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

    run_status = run.status if run else PayrollRunStatus.DRAFT
    can_prepare = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_PREPARE))
    can_review = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_REVIEW))
    can_approve = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_PAYROLL_RUNS_APPROVE))
    attendance_calculable = attendance_status in {AttendancePeriodStatus.APPROVED.label, AttendancePeriodStatus.LOCKED.label}
    attendance_locked = attendance_status == AttendancePeriodStatus.LOCKED.label
    source_clear = not source_errors and not any(row.get("blockers") for row in rows)
    review_signed_off = bool(run and run.reviewed_at and run.reviewed_by_id)
    allowed_actions: list[str] = []
    if can_prepare and run_status in {PayrollRunStatus.DRAFT, PayrollRunStatus.CALCULATED} and attendance_calculable and source_clear:
        allowed_actions.append("calculate")
    if can_prepare and run_status == PayrollRunStatus.CALCULATED:
        allowed_actions.append("reset")
        if attendance_locked and source_clear:
            allowed_actions.append("submit_review")
    if can_review and run_status == PayrollRunStatus.REVIEW:
        allowed_actions.append("return_for_changes")
        if attendance_locked and source_clear and not review_signed_off:
            allowed_actions.append("review")
    if can_approve and run_status == PayrollRunStatus.REVIEW and review_signed_off and attendance_locked and source_clear:
        allowed_actions.append("approve")
    next_action = next((item for item in ("calculate", "submit_review", "review", "approve") if item in allowed_actions), None)

    return {
        "run": _run_payload(run, period_start=start, membership=membership),
        "rows": rows,
        "sourceErrors": source_errors,
        "policy": serialize_payroll_policy(policy),
        "adjustments": [serialize_payroll_adjustment(item) for item in adjustments],
        "adjustmentsByEmployee": adjustments_by_employee,
        "reviewHistory": _audit_history(run),
        "attendanceStatus": attendance_status,
        "attendanceLocked": attendance_locked,
        "workflow": {
            "statusValue": run_status,
            "allowedActions": allowed_actions,
            "nextAction": next_action,
            "canCalculate": "calculate" in allowed_actions,
            "canReset": "reset" in allowed_actions,
            "canSubmitReview": "submit_review" in allowed_actions,
            "canReview": "review" in allowed_actions,
            "reviewSignedOff": review_signed_off,
            "canReturnForChanges": "return_for_changes" in allowed_actions,
            "canApprove": "approve" in allowed_actions,
            "sourceClear": source_clear,
            "attendanceCalculable": attendance_calculable,
            "attendanceLocked": attendance_locked,
        },
        "previous": {
            "period": f"{previous_start:%Y-%m}",
            "label": _period_label(previous_start),
            "run": _run_payload(previous_run, period_start=previous_start, membership=membership) if previous_run else None,
            "rows": previous_rows,
        },
    }
