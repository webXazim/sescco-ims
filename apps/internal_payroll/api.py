from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.http import HttpRequest, JsonResponse
from django.db.models import Count, Prefetch, Q
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.api_permissions import api_workspace_required
from apps.accounts.roles import Workspace
from apps.core.query_controls import apply_ordering, parse_list_controls, serialize_list
from apps.internal_payroll.api_utils import (
    handle_api_error as _handle_error,
    json_body as _json_body,
    parse_active_query as _active_query,
    parse_date as _date,
    parse_optional_date as _optional_date,
)
from apps.internal_payroll.models import (
    AttendanceEntry,
    AttendancePeriod,
    BankExportChannel,
    BankExportTemplate,
    Branch,
    Department,
    EmployeeOrganizationAssignment,
    EmployeePaymentProfile,
    EmploymentStatus,
    InternalEmployee,
    PayrollRun,
    SalaryStructure,
    SalaryStructureLine,
    WPSMapping,
)
from apps.internal_payroll.selectors import (
    branches_for_company,
    departments_for_company,
    employee_profile_context,
    employees_for_company,
    serialize_branch,
    serialize_department,
    serialize_employee,
    current_salary_structures_for_company,
)
from apps.internal_payroll.selectors.organization import serialize_assignment, serialize_employee_lifecycle
from apps.internal_payroll.selectors.payment import serialize_payment_profile
from apps.internal_payroll.services import (
    change_employee_organization,
    change_employee_lifecycle,
    archive_employee,
    archive_branch,
    archive_department,
    restore_employee_archive,
    restore_branch_archive,
    restore_department_archive,
    restore_branch_trash,
    restore_department_trash,
    restore_employee_trash,
    delete_unused_employee,
    delete_unused_branch,
    delete_unused_department,
    create_branch,
    create_department,
    create_employee,
    update_branch,
    update_department,
    update_employee,
)
from apps.internal_payroll.services.payment import payment_readiness



def _employee_profile_period(value: str) -> date:
    raw = (value or "").strip()
    if len(raw) == 7:
        raw = f"{raw}-01"
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({"period": "Period must use YYYY-MM format."}) from exc
    if parsed.day != 1:
        raise ValidationError({"period": "Period must identify a calendar month."})
    return parsed


def _employee_status_query(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized or normalized == "all":
        return ""
    allowed = {item.value for item in EmploymentStatus}
    if normalized not in allowed:
        raise ValidationError({"status": "Unknown employee status."})
    return normalized


def _employee_archived_query(value: str) -> bool | None:
    normalized = (value or "").strip().lower()
    if normalized in {"", "current", "false", "0", "no"}:
        return False
    if normalized in {"archived", "true", "1", "yes"}:
        return True
    if normalized == "all":
        return None
    raise ValidationError({"archived": "Archived filter must be current, archived, or all."})


def _employee_basic_salary_map(*, company, employee_ids) -> tuple[dict[str, str], set[str]]:
    employee_ids = [str(item) for item in employee_ids if item]
    if not employee_ids:
        return {}, set()
    as_of = timezone.localdate()
    basic_lines = SalaryStructureLine.objects.for_company(company).filter(
        wps_mapping=WPSMapping.BASIC_SALARY
    ).order_by("component_code")
    structures = (
        SalaryStructure.objects.for_company(company)
        .filter(employee_id__in=employee_ids, effective_from__lte=as_of)
        .filter(Q(effective_to__isnull=True) | Q(effective_to__gte=as_of))
        .prefetch_related(
            Prefetch("lines", queryset=basic_lines, to_attr="directory_basic_lines")
        )
        .order_by("employee_id", "-effective_from", "-created_at")
    )
    amounts: dict[str, str] = {}
    configured: set[str] = set()
    for structure in structures:
        employee_id = str(structure.employee_id)
        if employee_id in configured:
            continue
        configured.add(employee_id)
        line = next(iter(getattr(structure, "directory_basic_lines", [])), None)
        if line is not None:
            amounts[employee_id] = str(line.amount)
    return amounts, configured


def _employee_page_financial_context(*, company, employee_ids, period_value: str) -> tuple[dict[str, object], dict[str, str]]:
    employee_ids = [str(item) for item in employee_ids if item]
    if not employee_ids:
        return {}, {}
    profiles = {
        str(profile.employee_id): profile
        for profile in EmployeePaymentProfile.objects.for_company(company)
        .filter(employee_id__in=employee_ids)
        .select_related("employee", "verified_by")
    }
    statuses: dict[str, str] = {}
    if period_value:
        period_start = _employee_profile_period(period_value)
        run = PayrollRun.objects.for_company(company).filter(period_start=period_start).first()
        if run is not None:
            template = (
                BankExportTemplate.objects.for_company(company)
                .filter(channel=BankExportChannel.WPS, is_active=True, archived_at__isnull=True)
                .order_by("name")
                .first()
            )
            readiness = payment_readiness(
                company=company,
                run=run,
                channel=BankExportChannel.WPS,
                template=template,
                employee_ids=employee_ids,
            )
            for item in readiness.get("rows", []):
                statuses[str(item["line"].employee_id)] = "Ready" if not item.get("blockers") else "Blocked"
    for employee_id, profile in profiles.items():
        if employee_id in statuses:
            continue
        statuses[employee_id] = "Pending" if profile.is_active and profile.wps_enabled else "Not configured"
    return profiles, statuses


def _employee_scope_summary(*, company, branch_id=None, department_id=None, period_value: str = "") -> dict[str, object]:
    current = employees_for_company(
        company=company, branch_id=branch_id, department_id=department_id, archived=False
    )
    ids = current.values("pk")
    aggregate = current.aggregate(
        employee_count=Count("pk"),
        active_employee_count=Count("pk", filter=Q(status=EmploymentStatus.ACTIVE)),
    )
    salary_configured = (
        current_salary_structures_for_company(company=company)
        .filter(employee_id__in=ids)
        .values("employee_id")
        .distinct()
        .count()
    )
    wps_configured = (
        EmployeePaymentProfile.objects.for_company(company)
        .filter(employee_id__in=ids, is_active=True, wps_enabled=True)
        .count()
    )
    assignments = (
        EmployeeOrganizationAssignment.objects.for_company(company)
        .filter(employee_id__in=ids, effective_to__isnull=True)
        .filter(branch__deleted_at__isnull=True, branch__archived_at__isnull=True)
        .filter(department__deleted_at__isnull=True, department__archived_at__isnull=True)
    )
    department_distribution = list(
        assignments.values("department_id", "department__name")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("department__name")
    )
    branch_distribution = list(
        assignments.values("branch_id", "branch__name")
        .annotate(count=Count("employee_id", distinct=True))
        .order_by("branch__name")
    )
    attendance_entered = 0
    if period_value:
        period_start = _employee_profile_period(period_value)
        period = AttendancePeriod.objects.for_company(company).filter(period_start=period_start).first()
        if period is not None:
            attendance_entered = (
                AttendanceEntry.objects.for_company(company)
                .filter(period=period, employee_id__in=ids)
                .values("employee_id")
                .distinct()
                .count()
            )
    return {
        "employeeCount": int(aggregate.get("employee_count") or 0),
        "activeEmployeeCount": int(aggregate.get("active_employee_count") or 0),
        "salaryConfiguredCount": int(salary_configured),
        "wpsConfiguredCount": int(wps_configured),
        "attendanceEnteredCount": int(attendance_entered),
        "departmentDistribution": [
            {"id": str(item["department_id"]), "name": item["department__name"], "count": int(item["count"])}
            for item in department_distribution
        ],
        "branchDistribution": [
            {"id": str(item["branch_id"]), "name": item["branch__name"], "count": int(item["count"])}
            for item in branch_distribution
        ],
    }


@require_http_methods(["GET"])
@api_workspace_required(Workspace.INTERNAL)
def employee_summary_api(request: HttpRequest) -> JsonResponse:
    try:
        branch_id = request.GET.get("branch") or None
        department_id = request.GET.get("department") or None
        summary = _employee_scope_summary(
            company=request.company,
            branch_id=branch_id,
            department_id=department_id,
            period_value=str(request.GET.get("period", "")).strip(),
        )
        if branch_id is None and department_id is None:
            summary["archivedEmployeeCount"] = employees_for_company(
                company=request.company, archived=True
            ).count()
        return JsonResponse({"ok": True, "summary": summary})
    except Exception as exc:
        return _handle_error(exc)


def _organization_master_filter(value: str) -> tuple[bool | None, bool | None]:
    normalized = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in {"", "current"}:
        return None, False
    if normalized == "active":
        return True, False
    if normalized == "inactive":
        return False, False
    if normalized == "archived":
        return None, True
    if normalized == "all":
        return None, None
    raise ValidationError({"status": "Status filter must be Active, Inactive, Archived, or All."})


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def branches_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {
                "code": "code",
                "name": "name",
                "location": "location",
                "manager": "manager_name",
                "status": "is_active",
                "employees": "active_employee_count",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="code")
            active, archived = _organization_master_filter(request.GET.get("status", ""))
            rows = branches_for_company(
                company=request.company, query=request.GET.get("q", ""), active=active, archived=archived,
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_branch)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        branch = create_branch(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            location=str(body.get("location", "")),
            address=str(body.get("address", "")),
            manager_name=str(body.get("manager", "")),
            kind=str(body.get("kind", "branch")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        return JsonResponse({"ok": True, "branch": serialize_branch(branch)}, status=201)
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
def branch_detail_api(request: HttpRequest, branch_id) -> JsonResponse:
    try:
        body = _json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_branch(
                actor_membership=request.company_membership, branch_id=branch_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedBranchId": deleted_id})
        current = Branch.objects.for_company(request.company).get(pk=branch_id, deleted_at__isnull=True)
        branch = update_branch(
            actor_membership=request.company_membership,
            branch_id=branch_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            location=str(body.get("location", current.location)),
            address=str(body.get("address", current.address)),
            manager_name=str(body.get("manager", current.manager_name)),
            kind=str(body.get("kind", current.kind)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        return JsonResponse({"ok": True, "branch": serialize_branch(branch)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def branch_lifecycle_api(request: HttpRequest, branch_id) -> JsonResponse:
    try:
        body = _json_body(request); action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            branch = archive_branch(actor_membership=request.company_membership, branch_id=branch_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            branch = restore_branch_archive(actor_membership=request.company_membership, branch_id=branch_id, reason=str(body.get("reason", "")), request=request)
        elif action == "restore_trash":
            branch = restore_branch_trash(actor_membership=request.company_membership, branch_id=branch_id, request=request)
        else:
            raise ValidationError({"action": "Branch lifecycle action must be archive, restore archive, or restore trash."})
        return JsonResponse({"ok": True, "branch": serialize_branch(branch)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def departments_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {"code": "code", "name": "name", "status": "is_active", "employees": "active_employee_count"}
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="code")
            active, archived = _organization_master_filter(request.GET.get("status", ""))
            rows = departments_for_company(
                company=request.company, query=request.GET.get("q", ""), active=active, archived=archived,
            )
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)
            results, meta = serialize_list(rows, controls=controls, serializer=serialize_department)
            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        department = create_department(
            actor_membership=request.company_membership,
            code=str(body.get("code", "")),
            name=str(body.get("name", "")),
            notes=str(body.get("notes", "")),
            is_active=body.get("status", "Active"),
            request=request,
        )
        return JsonResponse({"ok": True, "department": serialize_department(department)}, status=201)
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
def department_detail_api(request: HttpRequest, department_id) -> JsonResponse:
    try:
        body = _json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_department(
                actor_membership=request.company_membership, department_id=department_id,
                confirmation=str(body.get("confirmation", "")), reason=str(body.get("reason", "")), request=request,
            )
            return JsonResponse({"ok": True, "deletedDepartmentId": deleted_id})
        current = Department.objects.for_company(request.company).get(pk=department_id, deleted_at__isnull=True)
        department = update_department(
            actor_membership=request.company_membership,
            department_id=department_id,
            code=str(body.get("code", current.code)),
            name=str(body.get("name", current.name)),
            notes=str(body.get("notes", current.notes)),
            is_active=body.get("status", "Active" if current.is_active else "Inactive"),
            request=request,
        )
        return JsonResponse({"ok": True, "department": serialize_department(department)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def department_lifecycle_api(request: HttpRequest, department_id) -> JsonResponse:
    try:
        body = _json_body(request); action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            department = archive_department(actor_membership=request.company_membership, department_id=department_id, reason=str(body.get("reason", "")), request=request)
        elif action in {"restore", "restore_archive"}:
            department = restore_department_archive(actor_membership=request.company_membership, department_id=department_id, reason=str(body.get("reason", "")), request=request)
        elif action == "restore_trash":
            department = restore_department_trash(actor_membership=request.company_membership, department_id=department_id, request=request)
        else:
            raise ValidationError({"action": "Department lifecycle action must be archive, restore archive, or restore trash."})
        return JsonResponse({"ok": True, "department": serialize_department(department)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["GET", "POST"])
@api_workspace_required(Workspace.INTERNAL)
def employees_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.method == "GET":
            allowed_sorts = {
                "employee": "employee_number",
                "name": "full_name",
                "joining": "joining_date",
                "status": "status",
            }
            controls = parse_list_controls(request, allowed_sorts=allowed_sorts, default_sort="employee")
            rows = employees_for_company(
                company=request.company,
                query=request.GET.get("q", ""),
                status=_employee_status_query(request.GET.get("status", "")),
                branch_id=request.GET.get("branch") or None,
                department_id=request.GET.get("department") or None,
                archived=_employee_archived_query(request.GET.get("archived", "")),
            )
            employee_id = str(request.GET.get("employee_id", "")).strip()
            if employee_id:
                rows = rows.filter(pk=employee_id)
            wps_filter = str(request.GET.get("wps", "")).strip().lower().replace(" ", "_")
            period_value = str(request.GET.get("period", "")).strip()
            wps_readiness_by_employee = None
            # WPS filtering is the one directory filter that must classify the matching
            # payroll population before employee pagination. Upgrade 1.0.75 keeps that
            # classification explicit, but no longer constructs the full salary-payment
            # shell (all profiles + all batches + all batch rows) merely to filter employees.
            if wps_filter and wps_filter != "all":
                if wps_filter not in {"ready", "needs_setup"}:
                    raise ValidationError({"wps": "WPS filter must be ready, needs_setup, or all."})
                if not period_value:
                    raise ValidationError({"period": "A payroll period is required for WPS filtering."})
                period_start = _employee_profile_period(period_value)
                run = PayrollRun.objects.for_company(request.company).filter(period_start=period_start).first()
                readiness_rows = []
                if run is not None:
                    template = (
                        BankExportTemplate.objects.for_company(request.company)
                        .filter(channel=BankExportChannel.WPS, is_active=True, archived_at__isnull=True)
                        .order_by("name")
                        .first()
                    )
                    readiness = payment_readiness(
                        company=request.company, run=run, channel=BankExportChannel.WPS, template=template
                    )
                    readiness_rows = list(readiness.get("rows", []))
                ready_ids = {
                    str(item["line"].employee_id)
                    for item in readiness_rows
                    if not item.get("blockers")
                }
                wps_readiness_by_employee = {
                    str(item["line"].employee_id): ("Ready" if not item.get("blockers") else "Blocked")
                    for item in readiness_rows
                }
                if wps_filter == "ready":
                    rows = rows.filter(pk__in=ready_ids)
                else:
                    rows = rows.exclude(pk__in=ready_ids)
            rows = apply_ordering(rows, controls=controls, allowed_sorts=allowed_sorts)

            results, meta = serialize_list(rows, controls=controls, serializer=serialize_employee)
            page_ids = [row.get("id") for row in results if row.get("id")]
            basic_salary_by_employee, salary_configured_ids = _employee_basic_salary_map(
                company=request.company, employee_ids=page_ids
            )

            profile_models, page_readiness = _employee_page_financial_context(
                company=request.company, employee_ids=page_ids, period_value=period_value
            )
            profiles = {
                employee_id: serialize_payment_profile(profile)
                for employee_id, profile in profile_models.items()
            }
            readiness_by_employee = {
                employee_id: (wps_readiness_by_employee or {}).get(employee_id, status)
                for employee_id, status in page_readiness.items()
            }
            if wps_readiness_by_employee is not None:
                for employee_id in page_ids:
                    readiness_by_employee.setdefault(
                        employee_id, wps_readiness_by_employee.get(employee_id, "Needs setup")
                    )

            for result in results:
                employee_id = str(result.get("id"))
                profile = profiles.get(employee_id)
                result["paymentProfile"] = profile
                result["bank"] = profile.get("bankName", "") if profile else ""
                result["account"] = profile.get("destinationMasked", "") if profile else ""
                result["paymentMethod"] = profile.get("destinationLabel", "") if profile else "Not set"
                if employee_id in readiness_by_employee:
                    result["wps"] = readiness_by_employee[employee_id]
                elif profile:
                    result["wps"] = "Pending" if profile.get("active") and profile.get("wpsEnabled") else "Not configured"
                else:
                    result["wps"] = "Needs setup"
                result["basicSalary"] = basic_salary_by_employee.get(employee_id)
                result["salaryConfigured"] = employee_id in salary_configured_ids

            return JsonResponse({"ok": True, "results": results, "meta": meta})
        body = _json_body(request)
        employee = create_employee(
            actor_membership=request.company_membership,
            employee_number=str(body.get("employee_number", "")),
            full_name=str(body.get("full_name", "")),
            joining_date=_date(body.get("joining_date"), "joining_date"),
            branch_id=body.get("branch_id"),
            department_id=body.get("department_id"),
            position=str(body.get("position", "")),
            status=str(body.get("status", "Active")),
            national_id=str(body.get("national_id", "")),
            phone=str(body.get("phone", "")),
            address=str(body.get("address", "")),
            employment_end_date=_optional_date(body.get("employment_end_date"), "employment_end_date"),
            request=request,
        )
        # A child master may be restored independently while its Branch/Department
        # parent is still in the 30-day Delete window.  Serialize that exact
        # recovered row with inherited lifecycle state instead of re-querying only
        # currently visible employees (which would turn a successful restore into
        # a misleading API 404/500 after the transaction committed).
        employee = employees_for_company(
            company=request.company, archived=None, deleted=None
        ).get(pk=employee.pk)
        history = employee.organization_history
        return JsonResponse(
            {
                "ok": True,
                "employee": serialize_employee(employee),
                "lifecycle": serialize_employee_lifecycle(employee),
                "history": [serialize_assignment(item) for item in history],
            },
            status=201,
        )
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["GET"])
@api_workspace_required(Workspace.INTERNAL)
def employee_profile_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        employee = employees_for_company(company=request.company, archived=None).get(pk=employee_id)
        period_start = _employee_profile_period(request.GET.get("period", ""))
        return JsonResponse({
            "ok": True,
            "employee": serialize_employee(employee),
            "profile": employee_profile_context(
                company=request.company,
                employee=employee,
                period_start=period_start,
            ),
        })
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["PATCH", "DELETE"])
@api_workspace_required(Workspace.INTERNAL)
def employee_detail_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = _json_body(request)
        if request.method == "DELETE":
            deleted_id = delete_unused_employee(
                actor_membership=request.company_membership,
                employee_id=employee_id,
                confirmation=str(body.get("confirmation", "")),
                reason=str(body.get("reason", "")),
                request=request,
            )
            return JsonResponse({"ok": True, "deletedEmployeeId": deleted_id})
        employee = InternalEmployee.objects.for_company(request.company).get(pk=employee_id, deleted_at__isnull=True)
        if "status" in body and _employee_status_query(str(body.get("status", ""))) not in {"", employee.status}:
            raise ValidationError({"status": "Use the employee lifecycle action to change employment status."})
        if "employment_end_date" in body:
            requested_end = _optional_date(body.get("employment_end_date"), "employment_end_date")
            if requested_end != employee.employment_end_date:
                raise ValidationError({"employment_end_date": "Use the employee lifecycle action to end employment."})
        employee = update_employee(
            actor_membership=request.company_membership,
            employee_id=employee_id,
            employee_number=str(body.get("employee_number", employee.employee_number)),
            full_name=str(body.get("full_name", employee.full_name)),
            joining_date=_date(body.get("joining_date", employee.joining_date.isoformat()), "joining_date"),
            status=str(body.get("status", employee.status)),
            national_id=str(body.get("national_id", employee.national_id)),
            phone=str(body.get("phone", employee.phone)),
            address=str(body.get("address", employee.address)),
            employment_end_date=_optional_date(
                body.get("employment_end_date", employee.employment_end_date.isoformat() if employee.employment_end_date else None),
                "employment_end_date",
            ),
            request=request,
        )
        employee = employees_for_company(company=request.company).get(pk=employee.pk)
        return JsonResponse({"ok": True, "employee": serialize_employee(employee), "lifecycle": serialize_employee_lifecycle(employee)})
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def employee_lifecycle_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = _json_body(request)
        action = str(body.get("action", "")).strip().lower().replace("-", "_")
        if action == "archive":
            employee = archive_employee(
                actor_membership=request.company_membership, employee_id=employee_id,
                reason=str(body.get("reason", "")), request=request,
            )
        elif action == "restore_archive":
            employee = restore_employee_archive(
                actor_membership=request.company_membership, employee_id=employee_id,
                reason=str(body.get("reason", "")), request=request,
            )
        elif action == "restore_trash":
            employee = restore_employee_trash(
                actor_membership=request.company_membership, employee_id=employee_id, request=request,
            )
        else:
            employee = change_employee_lifecycle(
                actor_membership=request.company_membership, employee_id=employee_id, action=action,
                effective_date=_optional_date(body.get("effective_date"), "effective_date"),
                reason=str(body.get("reason", "")), request=request,
            )
        employee = employees_for_company(company=request.company).get(pk=employee.pk)
        history = employee.organization_history
        return JsonResponse({
            "ok": True, "employee": serialize_employee(employee),
            "lifecycle": serialize_employee_lifecycle(employee),
            "history": [serialize_assignment(item) for item in history],
        })
    except Exception as exc:
        return _handle_error(exc)


@require_http_methods(["POST"])
@api_workspace_required(Workspace.INTERNAL)
def employee_organization_api(request: HttpRequest, employee_id) -> JsonResponse:
    try:
        body = _json_body(request)
        assignment = change_employee_organization(
            actor_membership=request.company_membership,
            employee_id=employee_id,
            branch_id=body.get("branch_id"),
            department_id=body.get("department_id"),
            position=str(body.get("position", "")),
            effective_from=_date(body.get("effective_from"), "effective_from"),
            reason=str(body.get("reason", "Organization change")),
            request=request,
        )
        employee = employees_for_company(company=request.company).get(pk=employee_id)
        history = employee.organization_history
        return JsonResponse(
            {
                "ok": True,
                "employee": serialize_employee(employee),
                "lifecycle": serialize_employee_lifecycle(employee),
                "assignment": serialize_assignment(assignment),
                "history": [serialize_assignment(item) for item in history],
            },
            status=201,
        )
    except Exception as exc:
        return _handle_error(exc)
