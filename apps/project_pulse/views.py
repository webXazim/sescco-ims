"""Scoped, permissioned Project Pulse pages and project-team administration."""
from django.contrib import messages
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseBadRequest, FileResponse
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_allows_project, membership_has_permission
from apps.accounts.models import CompanyMembership
from apps.projects.models import Project

from .access import (require_project_list_access, require_team_manage,
                     require_team_view, require_categories_view, require_categories_manage,
                     require_tasks_view, require_tasks_manage, require_progress_view,
                     require_progress_update, scoped_projects)
from .models import (PulseProjectTeamMember, PulseWorkCategory, PulseTask,
                     PulseProgressUpdate, PulseExpenseCategory, PulseExpenseEntry, PulseExpenseChange,
                     PulseExpensePayment, PulseExpenseAttachment)
from .expense_services import (save_expense_category, archive_expense_category,
                               save_expense, void_expense, expense_rollups,
                               submit_expense, review_expense, record_expense_payment,
                               void_expense_payment, upload_expense_attachment)
from .forms import PulseExpenseCategoryForm, PulseExpenseForm, PulseExpensePaymentForm
from .access import (require_expense_categories_view, require_expense_categories_manage,
                     require_expenses_view, require_expenses_manage, require_expenses_approve,
                     require_expense_payments_manage, require_expense_attachments_manage)
from .forms import PulseCategoryForm, PulseTaskForm, PulseProgressForm, PulseBudgetProposalForm
from .models import PulseBudgetRevision
from .budget_services import budget_rollups, propose_budget, review_budget
from .access import require_budgets_view, require_budgets_manage, require_budgets_approve
from apps.accounts.roles import AccessRole
from .access import (require_financials_view, require_contracts_manage,
                     require_contracts_approve, require_forecasts_manage, require_forecasts_approve)
from .forms import PulseContractForm, PulseVariationForm, PulseForecastForm
from .models import PulseContractRevision, PulseContractVariation, PulseCostForecast
from .commercial_services import (commercial_summary, propose_contract, review_contract,
    propose_variation, review_variation, propose_forecast, review_forecast)
from .work_services import save_category, set_category_archive, save_task, set_task_archive
from .services import assign_team_member, remove_team_member
from .progress_services import calculate_progress, can_update_task_progress, record_progress
from .access import require_reports_view, require_reports_export
from .report_services import PulseReportFilterForm, REPORT_TYPES, build_report, _authorized
from .report_exports import report_response
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event


def _context(request, *, page_key, title):
    member = request.company_membership
    return {
        "page_key": page_key,
        "page_title": title,
        "pulse_can_view_projects": membership_has_permission(member, AccessPermission.PULSE_PROJECTS_VIEW),
        "pulse_can_view_team": membership_has_permission(member, AccessPermission.PULSE_TEAM_VIEW),
        "pulse_can_manage_team": membership_has_permission(member, AccessPermission.PULSE_TEAM_MANAGE),
        "pulse_can_view_categories": membership_has_permission(member, AccessPermission.PULSE_CATEGORIES_VIEW),
        "pulse_can_manage_categories": membership_has_permission(member, AccessPermission.PULSE_CATEGORIES_MANAGE),
        "pulse_can_view_tasks": membership_has_permission(member, AccessPermission.PULSE_TASKS_VIEW),
        "pulse_can_manage_tasks": membership_has_permission(member, AccessPermission.PULSE_TASKS_MANAGE),
        "pulse_can_view_progress": membership_has_permission(member, AccessPermission.PULSE_TASKS_VIEW) and membership_has_permission(member, AccessPermission.PULSE_PROGRESS_VIEW),
        "pulse_can_update_progress": membership_has_permission(member, AccessPermission.PULSE_PROGRESS_UPDATE),
        "pulse_can_view_expense_categories": membership_has_permission(member, AccessPermission.PULSE_EXPENSE_CATEGORIES_VIEW),
        "pulse_can_manage_expense_categories": membership_has_permission(member, AccessPermission.PULSE_EXPENSE_CATEGORIES_MANAGE),
        "pulse_can_view_expenses": membership_has_permission(member, AccessPermission.PULSE_TASKS_VIEW) and membership_has_permission(member, AccessPermission.PULSE_EXPENSES_VIEW),
        "pulse_can_manage_expenses": membership_has_permission(member, AccessPermission.PULSE_EXPENSES_MANAGE),
        "pulse_can_approve_expenses": membership_has_permission(member, AccessPermission.PULSE_EXPENSES_APPROVE),
        "pulse_can_manage_payments": membership_has_permission(member, AccessPermission.PULSE_EXPENSE_PAYMENTS_MANAGE),
        "pulse_can_upload_attachments": membership_has_permission(member, AccessPermission.PULSE_EXPENSE_ATTACHMENTS_MANAGE),
        "pulse_can_view_budgets": all(membership_has_permission(member, p) for p in (AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_EXPENSES_VIEW, AccessPermission.PULSE_BUDGETS_VIEW)),
        "pulse_can_manage_budgets": membership_has_permission(member, AccessPermission.PULSE_BUDGETS_MANAGE),
        "pulse_can_approve_budgets": membership_has_permission(member, AccessPermission.PULSE_BUDGETS_APPROVE),
        "pulse_can_view_financials": all(membership_has_permission(member, p) for p in (
            AccessPermission.PULSE_PROJECTS_VIEW, AccessPermission.PULSE_TASKS_VIEW,
            AccessPermission.PULSE_EXPENSES_VIEW, AccessPermission.PULSE_BUDGETS_VIEW,
            AccessPermission.PULSE_FINANCIALS_VIEW)),
        "pulse_can_manage_contracts": membership_has_permission(member, AccessPermission.PULSE_CONTRACTS_MANAGE),
        "pulse_can_approve_contracts": membership_has_permission(member, AccessPermission.PULSE_CONTRACTS_APPROVE),
        "pulse_can_manage_forecasts": membership_has_permission(member, AccessPermission.PULSE_FORECASTS_MANAGE),
        "pulse_can_approve_forecasts": membership_has_permission(member, AccessPermission.PULSE_FORECASTS_APPROVE),
        "pulse_can_view_reports": membership_has_permission(member, AccessPermission.PULSE_REPORTS_VIEW),
        "pulse_can_export_reports": membership_has_permission(member, AccessPermission.PULSE_REPORTS_EXPORT),
    }


def _project_for_request(request, code):
    require_project_list_access(request)
    return get_object_or_404(scoped_projects(request), code__iexact=code)


def _active_team(project):
    return (PulseProjectTeamMember.objects.filter(project=project, is_active=True)
            .select_related("membership__user", "membership__access_profile").order_by("role", "membership__user__username"))


def _error_text(error):
    if hasattr(error, "message_dict"):
        return "; ".join(str(message) for values in error.message_dict.values() for message in values)
    return "; ".join(error.messages) if hasattr(error, "messages") else str(error)


@login_required
@require_GET
def home(request):
    projects = scoped_projects(request)
    counts = {
        "total": projects.count(),
        "active": projects.filter(status=Project.Status.ACTIVE).count(),
        "on_hold": projects.filter(status=Project.Status.ON_HOLD).count(),
        "completed": projects.filter(status=Project.Status.COMPLETED).count(),
    }
    # Overview access permits aggregate company/project-scope counts, not access
    # to individual project identifiers, clients or task details. That requires
    # the separate Projects / View grant. Never populate the template with named
    # projects for overview-only profiles (even if the links are hidden).
    can_view_projects = membership_has_permission(
        request.company_membership, AccessPermission.PULSE_PROJECTS_VIEW
    )
    visible_projects = (list(projects.exclude(status=Project.Status.ARCHIVED).order_by("code")[:12])
                        if can_view_projects else [])
    can_view_progress = can_view_projects and all(
        membership_has_permission(request.company_membership, p) for p in (
            AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW,
        )
    )
    if can_view_progress:
        summaries, _categories = calculate_progress([p.pk for p in visible_projects])
        for project in visible_projects:
            project.pulse_metrics = summaries.get(project.pk)
    visible_task_summary = None
    if can_view_progress:
        visible_task_summary = {
            "tasks": sum(p.pulse_metrics["task_count"] for p in visible_projects),
            "completed": sum(p.pulse_metrics["completed_count"] for p in visible_projects),
            "overdue": sum(p.pulse_metrics["overdue_count"] for p in visible_projects),
        }
    return render(request, "project_pulse/home.html", {
        **_context(request, page_key="pulse-home", title="Project Pulse"),
        "counts": counts, "projects": visible_projects,
        "visible_task_summary": visible_task_summary,
    })


@login_required
@require_GET
def project_list(request):
    projects = scoped_projects(request)
    require_project_list_access(request)
    search = request.GET.get("q", "").strip()[:120]
    status = request.GET.get("status", "").strip()
    if search:
        projects = projects.filter(
            Q(code__icontains=search) | Q(name__icontains=search)
            | Q(client_name__icontains=search) | Q(manager_name__icontains=search)
            | Q(location__icontains=search)
        )
    statuses = {code for code, _label in Project.Status.choices}
    if status in statuses:
        projects = projects.filter(status=status)
    elif status:
        status = ""
    page = Paginator(projects.order_by("code"), 25).get_page(request.GET.get("page"))
    if all(membership_has_permission(request.company_membership, p) for p in (
        AccessPermission.PULSE_TASKS_VIEW, AccessPermission.PULSE_PROGRESS_VIEW,
    )):
        summaries, _categories = calculate_progress([p.pk for p in page.object_list])
        for project in page.object_list:
            project.pulse_metrics = summaries.get(project.pk)
    return render(request, "project_pulse/project_list.html", {
        **_context(request, page_key="pulse-projects", title="Project Directory"),
        "projects": page, "search_query": search,
        "selected_status": status, "status_choices": Project.Status.choices,
    })


@login_required
@require_GET
def project_detail(request, code):
    project = _project_for_request(request, code)
    context = _context(request, page_key="pulse-projects", title=project.name)
    team = _active_team(project) if context["pulse_can_view_team"] else None
    categories = (list(PulseWorkCategory.objects.filter(project=project, archived_at__isnull=True)
        .annotate(task_count=Count("tasks", filter=Q(tasks__archived_at__isnull=True))))
        if context["pulse_can_view_categories"] else None)
    task_count = (PulseTask.objects.filter(category__project=project, archived_at__isnull=True,
        category__archived_at__isnull=True).count() if context["pulse_can_view_tasks"] else None)
    project_metrics = None
    if context["pulse_can_view_progress"]:
        project_summaries, category_summaries = calculate_progress([project.pk])
        project_metrics = project_summaries[project.pk]
        if categories is not None:
            for category in categories:
                category.pulse_metrics = category_summaries.get(category.pk)
    finance = expense_rollups(project) if context["pulse_can_view_expenses"] else None
    budget_summary = budget_rollups(project) if context["pulse_can_view_budgets"] else None
    commercial = commercial_summary(project) if context["pulse_can_view_financials"] else None
    if finance is not None and categories is not None:
        for category in categories:
            category.pulse_expense_total = finance["by_work_category"].get(category.pk)
    return render(request, "project_pulse/project_detail.html", {
        **context, "expense_summary": finance, "budget_summary": budget_summary, "commercial_summary": commercial, "project": project, "team": team, "categories": categories,
        "task_count": task_count, "project_metrics": project_metrics,
    })


@login_required
@require_GET
def project_team(request, code):
    require_team_view(request)
    project = _project_for_request(request, code)
    context = _context(request, page_key="pulse-team", title=f"{project.name} · Team")
    allowed_users = []
    if context["pulse_can_manage_team"] and project.status not in (Project.Status.ARCHIVED, Project.Status.COMPLETED):
        members = (CompanyMembership.objects.filter(
            company_id=project.company_id, is_active=True, user__is_active=True,
        ).select_related("user", "access_profile").prefetch_related("access_profile__permission_grants")
            .order_by("user__username"))
        for member in members:
            if (membership_has_permission(member, AccessPermission.PULSE_OVERVIEW_VIEW)
                and membership_has_permission(member, AccessPermission.PULSE_PROJECTS_VIEW)
                and membership_allows_project(member, project)):
                allowed_users.append(member)
    return render(request, "project_pulse/team.html", {
        **context, "project": project, "team": _active_team(project),
        "allowed_users": allowed_users,
        "team_can_edit_project": project.status not in (Project.Status.ARCHIVED, Project.Status.COMPLETED),
    })


@login_required
@require_POST
def project_team_assign(request, code):
    require_team_manage(request)
    project = _project_for_request(request, code)
    try:
        record = assign_team_member(
            actor=request.company_membership, project_id=project.pk,
            member_id=request.POST.get("membership_id", ""),
            role=request.POST.get("role", ""), request=request,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, f"{record.membership.user.display_name} assigned as {record.get_role_display().lower()}.")
    return redirect("project_pulse:project_team", code=project.code)


@login_required
@require_POST
def project_team_remove(request, code, member_id):
    require_team_manage(request)
    project = _project_for_request(request, code)
    record = remove_team_member(
        actor=request.company_membership, project_id=project.pk,
        team_member_id=member_id, request=request,
    )
    messages.success(request, f"{record.membership.user.display_name} removed from the project team.")
    return redirect("project_pulse:project_team", code=project.code)


def _pulse_work_editable(project):
    return project.deleted_at is None and project.archived_at is None and project.status == Project.Status.ACTIVE


def _category_for_request(project, category_id):
    return get_object_or_404(PulseWorkCategory.objects.filter(project=project), pk=category_id)


def _task_for_request(project, task_id):
    return get_object_or_404(PulseTask.objects.select_related(
        "category", "assigned_to__user",
    ).filter(category__project=project), pk=task_id)


@login_required
@require_GET
def work_categories(request, code):
    require_categories_view(request)
    project = _project_for_request(request, code)
    rows = list(PulseWorkCategory.objects.filter(project=project)
        .annotate(task_count=Count("tasks", filter=Q(tasks__archived_at__isnull=True)))
        .order_by("sort_order", "name", "pk"))
    context = _context(request, page_key="pulse-categories", title=f"{project.name} · Execution schedule")
    if context["pulse_can_view_progress"]:
        _, category_summaries = calculate_progress([project.pk])
        for category in rows:
            category.pulse_metrics = category_summaries.get(category.pk)
    return render(request, "project_pulse/categories.html", {
        **context,
        "project": project, "categories": rows, "work_editable": _pulse_work_editable(project),
    })


@login_required
def category_form(request, code, category_id=None):
    require_categories_manage(request)
    project = _project_for_request(request, code)
    row = _category_for_request(project, category_id) if category_id else None
    if not _pulse_work_editable(project) or (row and row.archived_at):
        raise PermissionDenied("Work categories are read-only in this state.")
    if request.method == "POST":
        form = PulseCategoryForm(request.POST, instance=row)
        if form.is_valid():
            try:
                result = save_category(
                    actor=request.company_membership, project_id=project.pk,
                    data=form.cleaned_data, category_id=category_id, request=request,
                )
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, f"Execution category {result.name} saved.")
                return redirect("project_pulse:categories", code=project.code)
    else:
        form = PulseCategoryForm(instance=row)
    return render(request, "project_pulse/category_form.html", {
        **_context(request, page_key="pulse-categories", title="Edit execution category" if row else "Add execution category"),
        "project": project, "category": row, "form": form,
    })


@login_required
@require_POST
def category_archive(request, code, category_id):
    require_categories_manage(request)
    project = _project_for_request(request, code)
    archive = request.POST.get("action") == "archive"
    if request.POST.get("action") not in ("archive", "restore"):
        return HttpResponseBadRequest("Invalid category archive action.")
    try:
        set_category_archive(actor=request.company_membership, project_id=project.pk,
                             category_id=category_id, archive=archive, request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Work category archived." if archive else "Work category restored.")
    return redirect("project_pulse:categories", code=project.code)


@login_required
@require_GET
def task_list(request, code):
    require_tasks_view(request)
    project = _project_for_request(request, code)
    archived = request.GET.get("archived") == "1"
    rows = PulseTask.objects.filter(category__project=project).select_related(
        "category", "assigned_to__user"
    )
    if archived:
        rows = rows.filter(Q(archived_at__isnull=False) | Q(category__archived_at__isnull=False))
    else:
        rows = rows.filter(archived_at__isnull=True, category__archived_at__isnull=True)
    category_value = request.GET.get("category", "").strip()
    if category_value.isdecimal():
        rows = rows.filter(category_id=int(category_value))
    else:
        category_value = ""
    status = request.GET.get("status", "").strip()
    if status in PulseTask.Status.values:
        rows = rows.filter(status=status)
    else:
        status = ""
    search = request.GET.get("q", "").strip()[:120]
    if search:
        rows = rows.filter(Q(title__icontains=search) | Q(description__icontains=search))
    page = Paginator(rows.order_by("sort_order", "due_date", "pk"), 35).get_page(request.GET.get("page"))
    context = _context(request, page_key="pulse-tasks", title=f"{project.name} · Scheduled works")
    if context["pulse_can_view_progress"]:
        for task in page.object_list:
            task.pulse_can_update = (context["pulse_can_update_progress"] and
                _pulse_work_editable(project) and task.archived_at is None and
                task.category.archived_at is None and
                can_update_task_progress(request.company_membership, task))
    return render(request, "project_pulse/tasks.html", {
        **context,
        "project": project, "tasks": page, "search_query": search,
        "categories": PulseWorkCategory.objects.filter(project=project).order_by("sort_order", "name"),
        "selected_category": category_value, "selected_status": status,
        "statuses": PulseTask.Status.choices, "show_archived": archived,
        "work_editable": _pulse_work_editable(project), "today": timezone.localdate(),
    })


@login_required
@require_GET
def my_tasks(request):
    require_tasks_view(request)
    rows = (PulseTask.objects.filter(
        assigned_to=request.company_membership, category__project__in=scoped_projects(request),
        category__project__pulse_team_members__membership=request.company_membership,
        category__project__pulse_team_members__is_active=True,
        archived_at__isnull=True, category__archived_at__isnull=True,
    ).select_related("category__project").order_by("due_date", "pk"))
    page = Paginator(rows, 35).get_page(request.GET.get("page"))
    context = _context(request, page_key="pulse-my-tasks", title="My Tasks")
    if context["pulse_can_view_progress"]:
        for task in page.object_list:
            task.pulse_can_update = (context["pulse_can_update_progress"] and
                _pulse_work_editable(task.category.project) and
                can_update_task_progress(request.company_membership, task))
    return render(request, "project_pulse/my_tasks.html", {
        **context,
        "tasks": page, "today": timezone.localdate(),
    })


@login_required
def task_form(request, code, task_id=None):
    require_tasks_manage(request)
    project = _project_for_request(request, code)
    row = _task_for_request(project, task_id) if task_id else None
    if not _pulse_work_editable(project) or (row and (row.archived_at or row.category.archived_at)):
        raise PermissionDenied("Tasks cannot be edited in this state.")
    if request.method == "POST":
        form = PulseTaskForm(request.POST, instance=row, project=project)
        if form.is_valid():
            try:
                result = save_task(actor=request.company_membership, project_id=project.pk,
                                   data=form.cleaned_data, task_id=task_id, request=request)
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, f"Scheduled work {result.title} saved.")
                return redirect("project_pulse:tasks", code=project.code)
    else:
        form = PulseTaskForm(instance=row, project=project)
        selected_category = request.GET.get("category", "")
        if not row and selected_category.isdecimal() and form.fields["category"].queryset.filter(pk=int(selected_category)).exists():
            form.initial["category"] = int(selected_category)
    return render(request, "project_pulse/task_form.html", {
        **_context(request, page_key="pulse-tasks", title="Edit scheduled work" if row else "New scheduled work"),
        "project": project, "task": row, "form": form,
    })


@login_required
@require_POST
def task_archive(request, code, task_id):
    require_tasks_manage(request)
    project = _project_for_request(request, code)
    action = request.POST.get("action")
    if action not in ("archive", "restore"):
        return HttpResponseBadRequest("Invalid task archive action.")
    try:
        set_task_archive(actor=request.company_membership, project_id=project.pk,
                         task_id=task_id, archive=(action == "archive"), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Task archived." if action == "archive" else "Task restored.")
    return redirect("project_pulse:tasks", code=project.code)


@login_required
@require_GET
def task_progress(request, code, task_id):
    require_progress_view(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    editable = _pulse_work_editable(project) and task.archived_at is None and task.category.archived_at is None
    can_update = (editable and membership_has_permission(request.company_membership, AccessPermission.PULSE_PROGRESS_UPDATE)
                  and can_update_task_progress(request.company_membership, task))
    history = (PulseProgressUpdate.objects.filter(task=task)
        .select_related("updated_by__user").order_by("-created_at", "-pk")[:100])
    return render(request, "project_pulse/task_progress.html", {
        **_context(request, page_key="pulse-tasks", title=f"{task.title} · Execution history"),
        "project": project, "task": task, "history": history, "can_update_task": can_update,
        "progress_form": PulseProgressForm(initial={"status": task.status}),
    })


@login_required
@require_POST
def task_progress_update(request, code, task_id):
    require_progress_update(request)
    project = _project_for_request(request, code)
    form = PulseProgressForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(
            f"{field}: {error}" for field, errors in form.errors.items() for error in errors
        ))
        return redirect("project_pulse:task_progress", code=project.code, task_id=task_id)
    try:
        record_progress(
            actor=request.company_membership, project_id=project.pk, task_id=task_id,
            progress_percent=100 if form.cleaned_data["status"] == PulseTask.Status.COMPLETED else 0,
            status=form.cleaned_data["status"], note=form.cleaned_data["note"], request=request,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Scheduled work status saved in the execution history.")
    return redirect("project_pulse:task_progress", code=project.code, task_id=task_id)



@login_required
@require_POST
def task_completion(request, code, task_id):
    """Quick complete/reopen from the execution schedule, with an audit trail."""
    require_progress_update(request)
    project = _project_for_request(request, code)
    action = request.POST.get("action", "")
    if action not in ("complete", "reopen"):
        return HttpResponseBadRequest("Invalid scheduled work completion action.")
    status = (PulseTask.Status.COMPLETED if action == "complete"
              else PulseTask.Status.NOT_STARTED)
    existing = _task_for_request(project, task_id)
    if existing.status == PulseTask.Status.CANCELLED:
        messages.error(request, "Cancelled scheduled works cannot be completed from this shortcut.")
        return redirect("project_pulse:scheduled_works", code=project.code)
    try:
        record_progress(
            actor=request.company_membership, project_id=project.pk,
            task_id=task_id, status=status,
            progress_percent=100 if action == "complete" else 0,
            note="Completed from execution schedule." if action == "complete" else "Reopened from execution schedule.",
            request=request,
        )
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Scheduled work completed." if action == "complete" else "Scheduled work reopened.")
    # Always go to the category schedule; never trust a user-supplied redirect.
    task = _task_for_request(project, task_id)
    if membership_has_permission(request.company_membership, AccessPermission.PULSE_CATEGORIES_VIEW):
        return redirect("project_pulse:category_detail", code=project.code, category_id=task.category_id)
    return redirect("project_pulse:scheduled_works", code=project.code)


@login_required
@require_GET
def category_detail(request, code, category_id):
    """The category's schedule, status and permitted financial summaries."""
    require_categories_view(request)
    project = _project_for_request(request, code)
    category = _category_for_request(project, category_id)
    context = _context(request, page_key="pulse-categories", title=f"{category.name} · Execution schedule")
    scheduled = []
    page = None
    if context["pulse_can_view_tasks"]:
        qs = (PulseTask.objects.filter(category=category, archived_at__isnull=True)
              .exclude(status=PulseTask.Status.CANCELLED)
              .order_by("sort_order", "due_date", "pk"))
        page = Paginator(qs, 50).get_page(request.GET.get("page"))
        scheduled = list(page.object_list)
        editable = _pulse_work_editable(project) and category.archived_at is None
        for item in scheduled:
            item.pulse_can_update = (editable and context["pulse_can_update_progress"]
                                     and context["pulse_can_view_progress"]
                                     and can_update_task_progress(request.company_membership, item))
    _, category_metrics = calculate_progress([project.pk])
    metric = category_metrics.get(category.pk)
    expenses = None
    if context["pulse_can_view_expenses"]:
        expenses = expense_rollups(project)["approved_by_work_category"].get(category.pk, 0)
    budget = None
    if context["pulse_can_view_budgets"]:
        budget = next((row for row in budget_rollups(project)["rows"]
                       if row["category"].pk == category.pk), None)
    return render(request, "project_pulse/category_detail.html", {
        **context, "project": project, "category": category, "scheduled": scheduled,
        "page": page, "metrics": metric, "approved_expenses": expenses,
        "budget_row": budget,
        "work_editable": _pulse_work_editable(project) and category.archived_at is None,
    })


@login_required
@require_GET
def expense_categories(request, code):
    require_expense_categories_view(request)
    project = _project_for_request(request, code)
    rows = PulseExpenseCategory.objects.filter(project=project).order_by("sort_order", "name")
    return render(request, "project_pulse/expense_categories.html", {
        **_context(request, page_key="pulse-expense-categories", title="Expense categories"),
        "project": project, "categories": rows,
        "work_editable": _pulse_work_editable(project),
    })


@login_required
def expense_category_form(request, code, category_id=None):
    require_expense_categories_manage(request)
    project = _project_for_request(request, code)
    row = get_object_or_404(PulseExpenseCategory, project=project, pk=category_id) if category_id else None
    if not _pulse_work_editable(project) or (row and row.archived_at):
        raise PermissionDenied("Expense categories cannot be modified in this project state.")
    if request.method == "POST":
        form = PulseExpenseCategoryForm(request.POST, instance=row)
        if form.is_valid():
            try:
                record = save_expense_category(actor=request.company_membership, project_id=project.pk,
                    category_id=category_id, data=form.cleaned_data, request=request)
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, f"Expense category {record.name} saved.")
                return redirect("project_pulse:expense_categories", code=project.code)
    else:
        form = PulseExpenseCategoryForm(instance=row)
    return render(request, "project_pulse/expense_category_form.html", {
        **_context(request, page_key="pulse-expense-categories", title="Edit expense category" if row else "New expense category"),
        "project": project, "category": row, "form": form,
    })


@login_required
@require_POST
def expense_category_archive(request, code, category_id):
    require_expense_categories_manage(request)
    project = _project_for_request(request, code)
    action = request.POST.get("action")
    if action not in ("archive", "restore"):
        return HttpResponseBadRequest("Invalid expense category action.")
    try:
        archive_expense_category(actor=request.company_membership, project_id=project.pk,
                                 category_id=category_id, archive=(action == "archive"), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Expense category status updated.")
    return redirect("project_pulse:expense_categories", code=project.code)


@login_required
@require_GET
def project_expenses(request, code):
    require_expenses_view(request)
    project = _project_for_request(request, code)
    rows = PulseExpenseEntry.objects.filter(task__category__project=project).select_related(
        "task__category", "expense_category", "recorded_by__user")
    category_id = request.GET.get("category", "").strip()
    task_id = request.GET.get("task", "").strip()
    if category_id.isdecimal():
        rows = rows.filter(expense_category_id=int(category_id))
    else:
        category_id = ""
    if task_id.isdecimal():
        rows = rows.filter(task_id=int(task_id))
    else:
        task_id = ""
    show_voided = request.GET.get("voided") == "1"
    rows = rows.filter(voided_at__isnull=not show_voided)
    selected_approval = request.GET.get("approval", "")
    if selected_approval in PulseExpenseEntry.ApprovalStatus.values:
        rows = rows.filter(approval_status=selected_approval)
    else:
        selected_approval = ""
    page = Paginator(rows.order_by("-expense_date", "-pk"), 40).get_page(request.GET.get("page"))
    summary = expense_rollups(project)
    work_categories = list(PulseWorkCategory.objects.filter(project=project).order_by("sort_order", "name"))
    for item in work_categories:
        item.pulse_expense_total = summary["approved_by_work_category"].get(item.pk)
    return render(request, "project_pulse/expenses.html", {
        **_context(request, page_key="pulse-expenses", title=f"{project.name} · Expenses"),
        "project": project, "entries": page, "summary": summary, "work_categories": work_categories,
        "expense_categories": PulseExpenseCategory.objects.filter(project=project).order_by("name"),
        "tasks": PulseTask.objects.filter(category__project=project).select_related("category").order_by("category__name", "title"),
        "selected_category": category_id, "selected_task": task_id, "show_voided": show_voided,
        "approval_choices": PulseExpenseEntry.ApprovalStatus.choices,
        "selected_approval": selected_approval,
    })


@login_required
@require_GET
def task_expenses(request, code, task_id):
    require_expenses_view(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    rows = PulseExpenseEntry.objects.filter(task=task).select_related("expense_category", "recorded_by__user")
    show_voided = request.GET.get("voided") == "1"
    rows = rows.filter(voided_at__isnull=not show_voided)
    page = Paginator(rows.order_by("-expense_date", "-pk"), 40).get_page(request.GET.get("page"))
    aggregate = expense_rollups(project)
    return render(request, "project_pulse/task_expenses.html", {
        **_context(request, page_key="pulse-expenses", title=f"{task.title} · Expenses"),
        "project": project, "task": task, "entries": page, "show_voided": show_voided,
        "total": aggregate["approved_by_task"].get(task.pk, 0),
        "recorded_total": aggregate["by_task"].get(task.pk, 0),
        "expense_breakdown": (PulseExpenseEntry.objects.filter(task=task, voided_at__isnull=True,
            approval_status=PulseExpenseEntry.ApprovalStatus.APPROVED)
            .values("expense_category__name").annotate(amount=Sum("amount")).order_by("expense_category__name")),
        "work_editable": _pulse_work_editable(project) and task.archived_at is None and task.category.archived_at is None,
    })


@login_required
def expense_form(request, code, task_id, expense_id=None):
    require_expenses_manage(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    row = get_object_or_404(PulseExpenseEntry, task=task, pk=expense_id) if expense_id else None
    if not _pulse_work_editable(project) or task.archived_at or task.category.archived_at or (row and (row.voided_at or row.approval_status not in (row.ApprovalStatus.DRAFT, row.ApprovalStatus.REJECTED))):
        raise PermissionDenied("Expenses cannot be edited in this state.")
    if request.method == "POST":
        form = PulseExpenseForm(request.POST, instance=row, project=project)
        if form.is_valid():
            try:
                save_expense(actor=request.company_membership, project_id=project.pk,
                    task_id=task.pk, expense_id=expense_id, data=form.cleaned_data, request=request)
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, "Expense recorded." if not row else "Expense updated.")
                return redirect("project_pulse:task_expenses", code=project.code, task_id=task.pk)
    else:
        form = PulseExpenseForm(instance=row, project=project,
                                initial={"expense_date": timezone.localdate()} if row is None else None)
    return render(request, "project_pulse/expense_form.html", {
        **_context(request, page_key="pulse-expenses", title="Edit expense" if row else "Record expense"),
        "project": project, "task": task, "expense": row, "form": form,
    })


@login_required
@require_POST
def expense_void(request, code, task_id, expense_id):
    require_expenses_manage(request)
    project = _project_for_request(request, code)
    try:
        void_expense(actor=request.company_membership, project_id=project.pk,
                     task_id=task_id, expense_id=expense_id,
                     reason=request.POST.get("reason", ""), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Expense voided. Historical record retained.")
    return redirect("project_pulse:task_expenses", code=project.code, task_id=task_id)


@login_required
@require_GET
def expense_history(request, code, task_id, expense_id):
    require_expenses_view(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    entry = get_object_or_404(PulseExpenseEntry.objects.select_related("expense_category"),
                              task=task, pk=expense_id)
    changes = PulseExpenseChange.objects.filter(entry=entry).select_related(
        "changed_by__user").order_by("-created_at", "-pk")
    return render(request, "project_pulse/expense_history.html", {
        **_context(request, page_key="pulse-expenses", title=f"{task.title} · Expense history"),
        "project": project, "task": task, "expense": entry, "changes": changes,
    })


@login_required
@require_GET
def expense_approvals(request, code):
    require_expenses_approve(request)
    project = _project_for_request(request, code)
    rows = PulseExpenseEntry.objects.filter(task__category__project=project, voided_at__isnull=True,
              approval_status=PulseExpenseEntry.ApprovalStatus.PENDING).select_related(
              "task__category", "expense_category", "recorded_by__user")
    return render(request, "project_pulse/expense_approvals.html", {
        **_context(request, page_key="pulse-expenses", title="Pending expense approvals"),
        "project": project, "entries": Paginator(rows, 40).get_page(request.GET.get("page")),
    })


@login_required
@require_GET
def expense_detail(request, code, task_id, expense_id):
    require_expenses_view(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    row = get_object_or_404(PulseExpenseEntry.objects.select_related("expense_category", "recorded_by__user", "reviewed_by__user"),
                            pk=expense_id, task=task)
    payments = list(PulseExpensePayment.objects.filter(entry=row).select_related("recorded_by__user", "voided_by__user"))
    paid = sum((entry.amount for entry in payments if not entry.voided_at), __import__("decimal").Decimal("0.00"))
    balance = row.amount - paid if row.approval_status == row.ApprovalStatus.APPROVED and not row.voided_at else None
    payment_state = ("Not eligible for payment" if balance is None else
                     "Paid" if balance == 0 else "Partially paid" if paid > 0 else "Unpaid")
    context = _context(request, page_key="pulse-expenses", title=f"Expense #{row.pk}")
    can_review_this = (context["pulse_can_approve_expenses"] and row.approval_status == row.ApprovalStatus.PENDING
        and not row.voided_at and (request.company_membership.pk != row.recorded_by_id or request.company_membership.role == "owner"))
    return render(request, "project_pulse/expense_detail.html", {
        **context, "project": project, "task": task, "entry": row,
        "payments": payments, "paid": paid, "balance": balance, "payment_state": payment_state,
        "attachments": row.attachments.select_related("uploaded_by__user"),
        "payment_form": PulseExpensePaymentForm(initial={"paid_on": timezone.localdate()}), "can_review_this": can_review_this,
        "work_editable": _pulse_work_editable(project),
        "payment_editable": project.deleted_at is None and project.archived_at is None and project.status != Project.Status.ARCHIVED,
    })


@login_required
@require_POST
def expense_submit(request, code, task_id, expense_id):
    require_expenses_manage(request)
    project = _project_for_request(request, code)
    try:
        submit_expense(actor=request.company_membership, project_id=project.pk,
            task_id=task_id, expense_id=expense_id, request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Expense submitted for approval.")
    return redirect("project_pulse:expense_detail", code=project.code, task_id=task_id, expense_id=expense_id)


@login_required
@require_POST
def expense_review(request, code, task_id, expense_id):
    require_expenses_approve(request)
    project = _project_for_request(request, code)
    action = request.POST.get("decision")
    if action not in ("approve", "reject"):
        return HttpResponseBadRequest("Choose approve or reject.")
    try:
        review_expense(actor=request.company_membership, project_id=project.pk,
            task_id=task_id, expense_id=expense_id, approve=action == "approve",
            note=request.POST.get("note", ""), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, f"Expense { 'approved' if action == 'approve' else 'rejected' }.")
    return redirect("project_pulse:expense_detail", code=project.code, task_id=task_id, expense_id=expense_id)


@login_required
@require_POST
def expense_payment_record(request, code, task_id, expense_id):
    require_expense_payments_manage(request)
    project = _project_for_request(request, code)
    form = PulseExpensePaymentForm(request.POST)
    if form.is_valid():
        try:
            record_expense_payment(actor=request.company_membership, project_id=project.pk,
                task_id=task_id, expense_id=expense_id, data=form.cleaned_data, request=request)
        except ValidationError as error:
            messages.error(request, _error_text(error))
        else:
            messages.success(request, "Payment recorded.")
    else:
        messages.error(request, "; ".join(str(m) for errors in form.errors.values() for m in errors))
    return redirect("project_pulse:expense_detail", code=project.code, task_id=task_id, expense_id=expense_id)


@login_required
@require_POST
def expense_payment_void(request, code, task_id, expense_id, payment_id):
    require_expense_payments_manage(request)
    project = _project_for_request(request, code)
    try:
        void_expense_payment(actor=request.company_membership, project_id=project.pk,
            task_id=task_id, expense_id=expense_id, payment_id=payment_id,
            reason=request.POST.get("reason", ""), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Payment voided; historical record retained.")
    return redirect("project_pulse:expense_detail", code=project.code, task_id=task_id, expense_id=expense_id)


@login_required
@require_POST
def expense_attachment_upload(request, code, task_id, expense_id):
    require_expense_attachments_manage(request)
    project = _project_for_request(request, code)
    upload = request.FILES.get("evidence")
    if not upload:
        messages.error(request, "Choose a PDF or image to upload.")
    else:
        try:
            upload_expense_attachment(actor=request.company_membership, project_id=project.pk,
                task_id=task_id, expense_id=expense_id, upload=upload, request=request)
        except ValidationError as error:
            messages.error(request, _error_text(error))
        else:
            messages.success(request, "Evidence uploaded into private storage.")
    return redirect("project_pulse:expense_detail", code=project.code, task_id=task_id, expense_id=expense_id)


@login_required
@require_GET
def expense_attachment_download(request, code, task_id, expense_id, attachment_id):
    require_expenses_view(request)
    project = _project_for_request(request, code)
    task = _task_for_request(project, task_id)
    row = get_object_or_404(PulseExpenseEntry, pk=expense_id, task=task)
    attachment = get_object_or_404(PulseExpenseAttachment, pk=attachment_id, entry=row)
    file = attachment.file.open("rb")
    response = FileResponse(file, as_attachment=True, filename=attachment.original_name,
                            content_type="application/octet-stream")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
@require_GET
def project_budgets(request, code):
    require_budgets_view(request)
    project = _project_for_request(request, code)
    summary = budget_rollups(project)
    revisions = (PulseBudgetRevision.objects.filter(category__project=project)
                 .select_related("category", "submitted_by__user", "reviewed_by__user")
                 .order_by("-submitted_at", "-pk"))
    context = _context(request, page_key="pulse-budgets", title=f"{project.name} · Budgets")
    page = Paginator(revisions, 25).get_page(request.GET.get("page"))
    for row in page.object_list:
        row.review_allowed = request.company_membership.role == AccessRole.OWNER or row.submitted_by_id != request.company_membership.pk
    return render(request, "project_pulse/budgets.html", {
        **context, "project": project, "summary": summary, "revisions": page,
        "project_editable": project.status == Project.Status.ACTIVE and not project.archived_at,
    })


@login_required
def budget_propose(request, code, category_id):
    require_budgets_manage(request)
    project = _project_for_request(request, code)
    category = get_object_or_404(PulseWorkCategory, pk=category_id, project=project)
    if project.status != Project.Status.ACTIVE or project.archived_at or category.archived_at:
        raise PermissionDenied("Budget revisions are restricted to active projects and categories.")
    if request.method == "POST":
        form = PulseBudgetProposalForm(request.POST)
        if form.is_valid():
            try:
                propose_budget(actor=request.company_membership, project_id=project.pk,
                    category_id=category.pk, amount=form.cleaned_data["amount"],
                    reason=form.cleaned_data["reason"], request=request)
            except ValidationError as error:
                form.add_error(None, _error_text(error))
            else:
                messages.success(request, "Budget proposal submitted for approval. The official budget has not changed.")
                return redirect("project_pulse:budgets", code=project.code)
    else:
        form = PulseBudgetProposalForm()
    return render(request, "project_pulse/budget_propose.html", {
        **_context(request, page_key="pulse-budgets", title="Propose budget"),
        "project": project, "category": category, "form": form,
    })


@login_required
@require_POST
def budget_review(request, code, revision_id):
    require_budgets_approve(request)
    project = _project_for_request(request, code)
    decision = request.POST.get("decision")
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Invalid budget review decision.")
    try:
        review_budget(actor=request.company_membership, project_id=project.pk,
            revision_id=revision_id, approve=(decision == "approve"),
            note=request.POST.get("note", ""), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, "Budget revision approved." if decision == "approve" else "Budget revision rejected.")
    return redirect("project_pulse:budgets", code=project.code)


# U08: explicitly authorized commercial workspaces; never embed these figures in
# shared search, general audit, or ordinary project/task API responses.
@login_required
@require_GET
def project_financials(request, code):
    require_financials_view(request)
    project = _project_for_request(request, code)
    context = _context(request, page_key="pulse-financials", title=f"{project.name} · Financial forecast")
    member = request.company_membership
    can_review_contracts = context["pulse_can_approve_contracts"]
    can_review_forecasts = context["pulse_can_approve_forecasts"]
    editable = project.status == Project.Status.ACTIVE and not project.archived_at
    contract_records = list(PulseContractRevision.objects.filter(project=project)
                            .select_related("submitted_by__user", "reviewed_by__user"))
    variations = list(PulseContractVariation.objects.filter(project=project)
                      .select_related("submitted_by__user", "reviewed_by__user"))
    forecasts = list(PulseCostForecast.objects.filter(project=project)
                     .select_related("submitted_by__user", "reviewed_by__user"))
    for rows, can_review in ((contract_records, can_review_contracts),
                             (variations, can_review_contracts),
                             (forecasts, can_review_forecasts)):
        for obj in rows:
            obj.can_review_in_ui = bool(editable and can_review and obj.status == obj.Status.PENDING and
                (member.role == AccessRole.OWNER or obj.submitted_by_id != member.pk))
    return render(request, "project_pulse/financials.html", {
        **context, "project": project, "financial": commercial_summary(project), "project_editable": editable,
        "contract_records": contract_records[:40], "variations": variations[:60], "forecasts": forecasts[:40],
    })


@login_required
def contract_propose(request, code):
    require_contracts_manage(request)
    project = _project_for_request(request, code)
    if project.status != Project.Status.ACTIVE or project.archived_at:
        raise PermissionDenied("Commercial proposals require an active project.")
    form = PulseContractForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            propose_contract(actor=request.company_membership, project_id=project.pk,
                amount=form.cleaned_data["amount"], reason=form.cleaned_data["reason"], request=request)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "Contract proposal submitted. Approved value has not changed.")
            return redirect("project_pulse:financials", code=project.code)
    return render(request, "project_pulse/financial_propose.html", {
        **_context(request, page_key="pulse-financials", title="Propose contract value"),
        "project": project, "form": form, "proposal_type": "contract",
        "heading": "Propose full base contract value",
    })


@login_required
def variation_propose(request, code):
    require_contracts_manage(request)
    project = _project_for_request(request, code)
    if project.status != Project.Status.ACTIVE or project.archived_at:
        raise PermissionDenied("Commercial proposals require an active project.")
    form = PulseVariationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            propose_variation(actor=request.company_membership, project_id=project.pk,
                amount=form.cleaned_data["amount"], description=form.cleaned_data["description"],
                reference=form.cleaned_data["reference"], reason=form.cleaned_data["reason"], request=request)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "Variation submitted for review.")
            return redirect("project_pulse:financials", code=project.code)
    return render(request, "project_pulse/financial_propose.html", {
        **_context(request, page_key="pulse-financials", title="Propose variation"),
        "project": project, "form": form, "proposal_type": "variation", "heading": "Propose contract variation",
    })


@login_required
def forecast_propose(request, code):
    require_forecasts_manage(request)
    project = _project_for_request(request, code)
    if project.status != Project.Status.ACTIVE or project.archived_at:
        raise PermissionDenied("Commercial proposals require an active project.")
    form = PulseForecastForm(request.POST or None, initial={"as_of_date": timezone.localdate()})
    if request.method == "POST" and form.is_valid():
        try:
            propose_forecast(actor=request.company_membership, project_id=project.pk,
                remaining_cost=form.cleaned_data["remaining_cost"], as_of_date=form.cleaned_data["as_of_date"],
                reason=form.cleaned_data["reason"], request=request)
        except ValidationError as error:
            form.add_error(None, _error_text(error))
        else:
            messages.success(request, "Remaining-cost forecast submitted for approval.")
            return redirect("project_pulse:financials", code=project.code)
    return render(request, "project_pulse/financial_propose.html", {
        **_context(request, page_key="pulse-financials", title="Propose cost forecast"),
        "project": project, "form": form, "proposal_type": "forecast", "heading": "Propose remaining-cost forecast",
    })


@login_required
@require_POST
def commercial_review(request, code, record_type, record_id):
    require_financials_view(request)
    if record_type in ("contract", "variation"):
        require_contracts_approve(request)
        reviewer = review_contract if record_type == "contract" else review_variation
    elif record_type == "forecast":
        require_forecasts_approve(request)
        reviewer = review_forecast
    else:
        return HttpResponseBadRequest("Unknown commercial record type.")
    project = _project_for_request(request, code)
    decision = request.POST.get("decision")
    if decision not in ("approve", "reject"):
        return HttpResponseBadRequest("Choose approve or reject.")
    try:
        reviewer(actor=request.company_membership, project_id=project.pk, record_id=record_id,
                 approve=decision == "approve", note=request.POST.get("note", ""), request=request)
    except ValidationError as error:
        messages.error(request, _error_text(error))
    else:
        messages.success(request, f"Commercial {record_type} { 'approved' if decision == 'approve' else 'rejected' }.")
    return redirect("project_pulse:financials", code=project.code)


# U09 report center: filtered reports are scoped to the selected project and
# re-authorized by report type both before display and before every export.
def _report_form_and_kind(request, project):
    params = request.GET.copy()
    available = []
    for kind, label in REPORT_TYPES:
        try:
            _authorized(project, request.company_membership, kind)
        except PermissionDenied:
            continue
        available.append((kind, label))
    if not available:
        raise PermissionDenied("Your profile has no permitted Project Pulse report types.")
    if not params.get('report'):
        params['report'] = available[0][0]
    kind = params['report']
    if kind not in dict(REPORT_TYPES):
        return PulseReportFilterForm(params, project=project), available
    # Explicitly fail closed for a type not authorized to this membership.
    _authorized(project, request.company_membership, kind)
    form = PulseReportFilterForm(params, project=project)
    form.fields['report'].choices = available
    return form, available


@login_required
@require_GET
def project_reports(request, code):
    project = _project_for_request(request, code)
    require_reports_view(request)
    form, available = _report_form_and_kind(request, project)
    report = None
    page = None
    if form.is_valid():
        try:
            report = build_report(project=project, actor=request.company_membership,
                                  filters=form.cleaned_data)
            page = Paginator(report.rows, 40).get_page(request.GET.get('page'))
        except ValidationError as exc:
            form.add_error(None, _error_text(exc))
    report_params = request.GET.copy()
    report_params.pop('page', None)
    return render(request, 'project_pulse/reports.html', {
        **_context(request, page_key='pulse-reports', title='Project Pulse reports'),
        'project': project, 'form': form, 'available_reports': available,
        'report_data': report, 'page': page,
        'query_string': report_params.urlencode(),
    }, status=200 if report is not None else 400)


@login_required
@require_GET
def project_report_export(request, code, format_name):
    project = _project_for_request(request, code)
    require_reports_export(request)
    if format_name not in ('xlsx', 'pdf'):
        return HttpResponseBadRequest('Use xlsx or pdf export.')
    form, _available = _report_form_and_kind(request, project)
    if not form.is_valid():
        return HttpResponseBadRequest('Invalid report filters. Return to Reports and correct the filter fields.')
    try:
        data = build_report(project=project, actor=request.company_membership,
                            filters=form.cleaned_data, export=True)
    except ValidationError as exc:
        return HttpResponseBadRequest(_error_text(exc))
    result = report_response(data, project, format_name)
    # Do not copy amounts, customer text, or commercial metrics to the general audit log.
    record_audit_event(company=project.company, area=AuditArea.PROJECTS,
        action='pulse.report.exported', object_type='projects.Project', object_id=project.pk,
        object_label=f'{project.code} · Restricted Project Pulse report export',
        actor_membership=request.company_membership, before={}, after={}, metadata={}, request=request)
    return result
