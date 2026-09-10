from __future__ import annotations

from calendar import month_name

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.context import access_context_for_request
from apps.accounts.permissions import (
    company_access_required,
    membership_can_workspace,
    membership_has_capability,
)
from apps.accounts.roles import Capability, Workspace
from apps.core.management import management_context
from apps.core.selectors.settings import company_settings
from apps.documents.selectors import document_context
from apps.internal_payroll.selectors import (
    attendance_period_context,
    internal_master_context,
    payroll_period_context,
    salary_payment_context,
    salary_setup_context,
)
from apps.rental_manpower.selectors import rental_master_context


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    absolute = year * 12 + (month - 1) + delta
    return absolute // 12, absolute % 12 + 1


def _period_options(*, months: int = 12) -> list[dict[str, str]]:
    today = timezone.localdate()
    rows: list[dict[str, str]] = []
    for offset in range(months):
        year, month = _shift_month(today.year, today.month, -offset)
        rows.append({"key": f"{year:04d}-{month:02d}", "label": f"{month_name[month]} {year}"})
    return rows


def _can_open_payroll_frontend(membership) -> bool:
    return any(
        membership_can_workspace(membership, workspace)
        for workspace in (Workspace.INTERNAL, Workspace.RENTAL, Workspace.MANAGEMENT)
    )


@login_required
@company_access_required
def payroll_app(request):
    """Render the merged DocGen V2 Payroll workspace against platform-owned data.

    Payroll keeps its dedicated rendering engine and namespaced assets, while Upgrade 10
    supplies the shared platform-level company/module switcher used by both Inventory and
    Payroll. Authentication, company context, projects, APIs and deployment remain unified.
    """

    membership = request.company_membership
    if not _can_open_payroll_frontend(membership):
        raise PermissionDenied("Your company role does not allow access to Payroll or workforce management.")

    access_context = access_context_for_request(request)
    display_name = request.user.display_name
    initials = "".join(part[0] for part in display_name.split()[:2]).upper() or "U"
    can_internal = membership_can_workspace(membership, Workspace.INTERNAL)
    can_rental = membership_can_workspace(membership, Workspace.RENTAL)
    can_management = membership_can_workspace(membership, Workspace.MANAGEMENT)

    # Keep the active Payroll workspace addressable in the URL.  The browser app still
    # switches workspaces without a full reload, but a real query parameter gives each
    # switcher item a reload-safe/no-JavaScript fallback and lets the server reject a
    # workspace that the current membership cannot open.
    requested_workspace = request.GET.get("workspace", "").strip().lower()
    allowed_workspace_keys = [
        key
        for key, allowed in (
            (Workspace.INTERNAL.value, can_internal),
            (Workspace.RENTAL.value, can_rental),
            (Workspace.MANAGEMENT.value, can_management),
        )
        if allowed
    ]
    initial_workspace = requested_workspace if requested_workspace in allowed_workspace_keys else None
    access_context["initial_workspace"] = initial_workspace

    internal_context = (
        internal_master_context(company=request.company)
        if can_internal
        else {"branches": [], "departments": [], "employees": [], "employeeOrganizationHistory": {}}
    )
    salary_context = (
        salary_setup_context(company=request.company)
        if can_internal
        else {
            "salaryComponents": [],
            "overtimePolicies": [],
            "salaryStructures": {},
            "salaryStructureHistory": {},
            "asOf": None,
        }
    )

    current_month = timezone.localdate().replace(day=1)
    attendance_context = (
        attendance_period_context(
            company=request.company,
            period_start=current_month,
            membership=membership,
        )
        if can_internal
        else {
            "period": {
                "id": None,
                "exists": False,
                "period": f"{current_month:%Y-%m}",
                "label": f"{month_name[current_month.month]} {current_month.year}",
                "status": "Draft",
                "statusValue": "draft",
                "canEdit": False,
                "canApprove": False,
                "nextAction": None,
            },
            "roster": [],
            "records": {},
            "overtime": {},
            "summary": {},
        }
    )
    payroll_context = (
        payroll_period_context(
            company=request.company,
            period_start=current_month,
            membership=membership,
        )
        if can_internal
        else {
            "run": {
                "id": None,
                "exists": False,
                "period": f"{current_month:%Y-%m}",
                "label": f"{month_name[current_month.month]} {current_month.year}",
                "status": "Draft",
                "statusValue": "draft",
                "revision": 0,
                "canEdit": False,
                "canApprove": False,
                "totals": {},
            },
            "rows": [],
            "sourceErrors": [],
            "policy": {
                "id": None,
                "prorationMethod": "not_configured",
                "prorationLabel": "Not configured",
                "configured": False,
            },
            "adjustments": [],
            "adjustmentsByEmployee": {},
            "reviewHistory": [],
            "attendanceStatus": "Not available",
            "attendanceLocked": False,
            "previous": {"period": None, "label": None, "run": None, "rows": []},
        }
    )

    rental_context = (
        rental_master_context(company=request.company)
        if can_rental
        else {
            "suppliers": [],
            "projects": [],
            "workers": [],
            "assignmentsByWorker": {},
            "assignmentAsOf": timezone.localdate().isoformat(),
            "assignmentSummary": {
                "assignmentSegments": 0,
                "currentlyAssigned": 0,
                "openEndedAssignments": 0,
            },
            "summary": {
                "supplierCount": 0,
                "activeSupplierCount": 0,
                "projectCount": 0,
                "activeProjectCount": 0,
                "workerCount": 0,
                "activeWorkerCount": 0,
            },
        }
    )

    documents_context = document_context(
        company=request.company,
        membership=membership,
    )
    management_bootstrap = (
        management_context(company=request.company, period_start=current_month)
        if can_management
        else {
            "period": f"{current_month:%Y-%m}",
            "periodLabel": f"{month_name[current_month.month]} {current_month.year}",
            "availablePeriods": [],
            "internal": {},
            "rental": {},
            "combined": None,
            "comparable": False,
            "headcount": {},
            "payments": {},
            "approvals": [],
            "audit": [],
        }
    )

    company_settings_row = company_settings(request.company)
    system_settings_context = {
        "companyName": request.company.name,
        "legalName": request.company.legal_name,
        "timezone": company_settings_row.timezone,
        "currency": company_settings_row.currency_code,
        "country": company_settings_row.country_code,
        "today": timezone.localdate().isoformat(),
        "canManage": membership_has_capability(membership, Capability.MANAGE_SETTINGS),
    }

    payment_context = (
        salary_payment_context(
            company=request.company,
            period_start=current_month,
            membership=membership,
        )
        if can_internal
        else {
            "period": f"{current_month:%Y-%m}",
            "settings": {},
            "profiles": {},
            "templates": [],
            "batches": [],
            "bankReadiness": {"ready": False, "companyBlockers": [], "employees": []},
            "wpsReadiness": {"ready": False, "companyBlockers": [], "employees": []},
            "canEditSetup": False,
            "canPay": False,
        }
    )

    return render(
        request,
        "payroll/app.html",
        {
            "access_context": access_context,
            "current_company": request.company,
            "current_membership": membership,
            "account_display_name": display_name,
            "account_initials": initials,
            "csrf_token": get_token(request),
            "internal_master_context": internal_context,
            "salary_setup_context": salary_context,
            "attendance_context": attendance_context,
            "payroll_context": payroll_context,
            "payment_context": payment_context,
            "rental_master_context": rental_context,
            "documents_context": documents_context,
            "management_context": management_bootstrap,
            "system_settings_context": system_settings_context,
            "period_options": _period_options(),
        },
    )
