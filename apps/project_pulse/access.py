"""Project Pulse company, project, and explicit profile authorization."""
from django.core.exceptions import PermissionDenied

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission, restrict_projects
from apps.projects.models import Project


def require_pulse_view(request):
    membership = getattr(request, "company_membership", None)
    company = getattr(request, "company", None)
    if company is None or not membership_has_permission(membership, AccessPermission.PULSE_OVERVIEW_VIEW):
        raise PermissionDenied("Project Pulse access is not granted to this profile.")
    return membership


def scoped_projects(request):
    membership = require_pulse_view(request)
    return restrict_projects(
        Project.objects.for_company(request.company).filter(deleted_at__isnull=True),
        membership,
    )


def require_project_list_access(request):
    if not membership_has_permission(
        getattr(request, "company_membership", None), AccessPermission.PULSE_PROJECTS_VIEW
    ):
        raise PermissionDenied("Project directory access is not granted to this profile.")


def require_team_view(request):
    require_project_list_access(request)
    if not membership_has_permission(
        getattr(request, "company_membership", None), AccessPermission.PULSE_TEAM_VIEW
    ):
        raise PermissionDenied("Project team viewing is not granted to this profile.")


def require_team_manage(request):
    require_team_view(request)
    if not membership_has_permission(
        getattr(request, "company_membership", None), AccessPermission.PULSE_TEAM_MANAGE
    ):
        raise PermissionDenied("Project team management is not granted to this profile.")


def require_categories_view(request):
    require_project_list_access(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_CATEGORIES_VIEW):
        raise PermissionDenied("Work category viewing is not granted to this profile.")


def require_categories_manage(request):
    require_categories_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_CATEGORIES_MANAGE):
        raise PermissionDenied("Work category management is not granted to this profile.")


def require_tasks_view(request):
    require_project_list_access(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_TASKS_VIEW):
        raise PermissionDenied("Task viewing is not granted to this profile.")


def require_tasks_manage(request):
    require_tasks_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_TASKS_MANAGE):
        raise PermissionDenied("Task management is not granted to this profile.")


def require_progress_view(request):
    require_tasks_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_PROGRESS_VIEW):
        raise PermissionDenied("Task progress viewing is not granted to this profile.")


def require_progress_update(request):
    require_progress_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_PROGRESS_UPDATE):
        raise PermissionDenied("Task progress updating is not granted to this profile.")



def require_expense_categories_view(request):
    require_project_list_access(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW):
        raise PermissionDenied("Expense category access is not granted to this profile.")


def require_expense_categories_manage(request):
    require_expense_categories_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE):
        raise PermissionDenied("Expense category management is not granted to this profile.")


def require_expenses_view(request):
    require_tasks_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSES_VIEW):
        raise PermissionDenied("Viewing expense amounts is not granted to this profile.")


def require_expenses_approve(request):
    require_expenses_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSES_APPROVE):
        raise PermissionDenied("Expense approval is not granted to this profile.")


def require_expense_payments_manage(request):
    require_expenses_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE):
        raise PermissionDenied("Expense payment management is not granted to this profile.")


def require_expense_attachments_manage(request):
    require_expenses_manage(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE):
        raise PermissionDenied("Expense document upload is not granted to this profile.")


def require_budgets_view(request):
    require_expenses_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_BUDGETS_VIEW):
        raise PermissionDenied("Viewing confidential project budgets is not permitted.")


def require_budgets_manage(request):
    require_budgets_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_BUDGETS_MANAGE):
        raise PermissionDenied("Proposing project budgets is not permitted.")


def require_budgets_approve(request):
    require_budgets_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_BUDGETS_APPROVE):
        raise PermissionDenied("Reviewing project budgets is not permitted.")


def require_expenses_manage(request):
    require_expenses_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_EXPENSES_MANAGE):
        raise PermissionDenied("Recording or editing expenses is not granted to this profile.")


def require_financials_view(request):
    require_budgets_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_FINANCIALS_VIEW):
        raise PermissionDenied("Contract values and profitability are restricted to authorized financial profiles.")


def require_contracts_manage(request):
    require_financials_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_CONTRACTS_MANAGE):
        raise PermissionDenied("Contract proposal permission is required.")


def require_contracts_approve(request):
    require_financials_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_CONTRACTS_APPROVE):
        raise PermissionDenied("Contract approval permission is required.")


def require_forecasts_manage(request):
    require_financials_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_FORECASTS_MANAGE):
        raise PermissionDenied("Forecast proposal permission is required.")


def require_forecasts_approve(request):
    require_financials_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_FORECASTS_APPROVE):
        raise PermissionDenied("Forecast approval permission is required.")


def require_reports_view(request):
    require_project_list_access(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_REPORTS_VIEW):
        raise PermissionDenied("Project Pulse reports are not granted to this profile.")


def require_reports_export(request):
    require_reports_view(request)
    if not membership_has_permission(getattr(request, "company_membership", None), AccessPermission.PULSE_REPORTS_EXPORT):
        raise PermissionDenied("Project Pulse report export is not granted to this profile.")
