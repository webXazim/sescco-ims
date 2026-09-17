from __future__ import annotations

from calendar import month_name
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Prefetch, Q, Sum

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.core.models import Company
from apps.core.payroll_attendance_contract import ATTENDANCE_WORKSPACE_INTERNAL, attendance_contract_payload
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
    salary_lines = SalaryStructureLine.objects.for_company(company).order_by("component_category", "component_code")
    salary_structures = (
        SalaryStructure.objects.for_company(company)
        .filter(effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=end))
        .prefetch_related(Prefetch("lines", queryset=salary_lines, to_attr="attendance_salary_lines"))
        .order_by("-effective_from", "-created_at")
    )
    return list(
        operational_internal_employees(company=company)
        .filter(joining_date__lte=end)
        .filter(Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=start))
        .exclude(status=EmploymentStatus.INACTIVE)
        .prefetch_related(
            Prefetch("organization_assignments", queryset=assignments, to_attr="attendance_org_history"),
            Prefetch("salary_structures", queryset=salary_structures, to_attr="attendance_salary_structures"),
        )
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
    can_edit = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_ATTENDANCE_EDIT) and status == AttendancePeriodStatus.DRAFT)
    can_submit = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_ATTENDANCE_SUBMIT) and status == AttendancePeriodStatus.DRAFT)
    can_approve = bool(membership and membership_has_permission(membership, AccessPermission.INTERNAL_ATTENDANCE_APPROVE))
    if status == AttendancePeriodStatus.DRAFT:
        next_action = "submit" if can_submit else None
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
        "canSubmit": can_submit,
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
    prefetched = getattr(employee, "attendance_salary_structures", None)
    if prefetched is not None:
        return next(
            (
                item
                for item in prefetched
                if item.effective_from <= as_of and (item.effective_to is None or item.effective_to >= as_of)
            ),
            None,
        )
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
    overtime_rate = (base_line.amount / divisor * multiplier).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
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


def _attendance_roster_queryset(*, company: Company, period_start: date):
    start, end = month_bounds(period_start)
    assignments = (
        EmployeeOrganizationAssignment.objects.for_company(company)
        .select_related("branch", "department")
        .filter(effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
        .order_by("-effective_from", "-created_at")
    )
    salary_lines = SalaryStructureLine.objects.for_company(company).order_by("component_category", "component_code")
    salary_structures = (
        SalaryStructure.objects.for_company(company)
        .filter(effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=end))
        .prefetch_related(Prefetch("lines", queryset=salary_lines, to_attr="attendance_salary_lines"))
        .order_by("-effective_from", "-created_at")
    )
    return (
        operational_internal_employees(company=company)
        .filter(joining_date__lte=end)
        .filter(Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=start))
        .exclude(status=EmploymentStatus.INACTIVE)
        .prefetch_related(
            Prefetch("organization_assignments", queryset=assignments, to_attr="attendance_org_history"),
            Prefetch("salary_structures", queryset=salary_structures, to_attr="attendance_salary_structures"),
        )
        .order_by("employee_number", "full_name")
    )


def attendance_period_summary(*, company: Company, period_start: date) -> dict[str, object]:
    """Return bounded aggregate facts without materializing the whole employee month."""
    start, end = month_bounds(period_start)
    period = attendance_period_for_company(company=company, period_start=start)
    base = (
        operational_internal_employees(company=company)
        .filter(joining_date__lte=end)
        .filter(Q(employment_end_date__isnull=True) | Q(employment_end_date__gte=start))
        .exclude(status=EmploymentStatus.INACTIVE)
    )
    required_days = 0
    for joining_date, employment_end_date in base.values_list("joining_date", "employment_end_date"):
        employed_from = max(joining_date, start)
        employed_to = min(employment_end_date or end, end)
        if employed_to >= employed_from:
            required_days += (employed_to - employed_from).days + 1
    entry_count = 0
    regular_hours = Decimal("0")
    absent_count = 0
    leave_count = 0
    overtime_count = 0
    overtime_hours = Decimal("0")
    overtime_amount = Decimal("0")
    if period is not None:
        entry_qs = AttendanceEntry.objects.for_company(company).filter(period=period)
        entry_count = entry_qs.count()
        regular_hours = entry_qs.aggregate(total=Sum("regular_hours")).get("total") or Decimal("0")
        absent_count = entry_qs.filter(code="A").count()
        leave_count = entry_qs.filter(code__in=("L", "S")).count()
        overtime_agg = AttendanceOvertimeEntry.objects.for_company(company).filter(period=period).aggregate(
            hours=Sum("hours"), amount=Sum("amount")
        )
        # Sum(1) is not portable across every supported backend; use count() for the row count.
        overtime_count = AttendanceOvertimeEntry.objects.for_company(company).filter(period=period).count()
        overtime_hours = overtime_agg.get("hours") or Decimal("0")
        overtime_amount = overtime_agg.get("amount") or Decimal("0")
    return {
        "employeeCount": base.count(),
        "entryCount": entry_count,
        "regularHours": str(regular_hours),
        "absentCount": absent_count,
        "leaveCount": leave_count,
        "missingCount": max(0, required_days - entry_count),
        "overtimeEmployees": overtime_count,
        "overtimeHours": str(overtime_hours),
        "overtimeAmount": str(overtime_amount),
    }


def attendance_period_context(
    *,
    company: Company,
    period_start: date,
    membership=None,
    query: str = "",
    branch: str = "",
    department: str = "",
    page: int | None = None,
    page_size: int | None = None,
    include_summary: bool = True,
) -> dict[str, object]:
    """Serialize one bounded attendance page.

    ``page``/``page_size`` are optional for backward compatibility with non-UI callers.  The
    Payroll UI always supplies them so 2k+ employee benchmark months never materialize the
    complete roster, daily entries and OT setup in one request.
    """
    start, end = month_bounds(period_start)
    period = attendance_period_for_company(company=company, period_start=start)
    roster_qs = _attendance_roster_queryset(company=company, period_start=start)

    period_assignments = (
        EmployeeOrganizationAssignment.objects.for_company(company)
        .filter(employee_id=OuterRef("pk"), effective_from__lte=end)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=start))
    )
    q = (query or "").strip()
    if q:
        assignment_search = period_assignments.filter(
            Q(position__icontains=q)
            | Q(branch__name__icontains=q)
            | Q(department__name__icontains=q)
        )
        roster_qs = roster_qs.annotate(_assignment_search_match=Exists(assignment_search)).filter(
            Q(employee_number__icontains=q)
            | Q(full_name__icontains=q)
            | Q(_assignment_search_match=True)
        )
    if branch:
        roster_qs = roster_qs.annotate(
            _branch_period_match=Exists(period_assignments.filter(branch__name=branch))
        ).filter(_branch_period_match=True)
    if department:
        roster_qs = roster_qs.annotate(
            _department_period_match=Exists(period_assignments.filter(department__name=department))
        ).filter(_department_period_match=True)

    if page is not None or page_size is not None:
        page_number = max(1, int(page or 1))
        bounded_size = max(1, min(100, int(page_size or 50)))
        paginator = Paginator(roster_qs, bounded_size)
        page_obj = paginator.get_page(page_number)
        roster = list(page_obj.object_list)
        meta = {
            "count": paginator.count,
            "page": page_obj.number,
            "pageSize": bounded_size,
            "totalPages": paginator.num_pages,
            "query": q,
            "branch": branch,
            "department": department,
        }
    else:
        roster = list(roster_qs)
        meta = {
            "count": len(roster), "page": None, "pageSize": None, "totalPages": None,
            "query": q, "branch": branch, "department": department,
        }

    employee_ids = [employee.pk for employee in roster]
    entries: list[AttendanceEntry] = []
    overtime_rows: list[AttendanceOvertimeEntry] = []
    if period is not None and employee_ids:
        entries = list(
            AttendanceEntry.objects.for_company(company)
            .filter(period=period, employee_id__in=employee_ids)
            .select_related("employee")
            .order_by("employee__employee_number", "work_date")
        )
        overtime_rows = list(
            AttendanceOvertimeEntry.objects.for_company(company)
            .filter(period=period, employee_id__in=employee_ids)
            .select_related("employee", "salary_structure")
            .order_by("employee__employee_number")
        )

    records: dict[str, dict[str, str]] = {}
    for entry in entries:
        records.setdefault(str(entry.employee_id), {})[str(entry.work_date.day)] = _display_attendance_value(entry)

    overtime_by_employee = {str(item.employee_id): item for item in overtime_rows}
    roster_payload: list[dict[str, object]] = []
    overtime_payload: dict[str, dict[str, object]] = {}
    for employee in roster:
        assignment = _employee_assignment_as_of(employee, end)
        employee_key = str(employee.pk)
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
        "attendanceContract": attendance_contract_payload(ATTENDANCE_WORKSPACE_INTERNAL),
        "period": serialize_attendance_period(period, period_start=start, membership=membership),
        "roster": roster_payload,
        "records": records,
        "overtime": overtime_payload,
        **({"summary": attendance_period_summary(company=company, period_start=start)} if include_summary else {}),
        "meta": meta,
    }
