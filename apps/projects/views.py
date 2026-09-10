from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.access import InventoryAdminRequiredMixin, InventoryWorkspaceMixin
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.trash import TRASH_RETENTION_DAYS, move_to_trash
from apps.inventory.models import StockItem
from apps.inventory.selectors import apply_stock_search, stock_movements

from .forms import ProjectForm
from .models import Project
from .selectors import project_list


def _project_snapshot(project: Project) -> dict[str, object]:
    return {
        "reference": str(project.reference),
        "code": project.code,
        "name": project.name,
        "client_name": project.client_name,
        "location": project.location,
        "manager_name": project.manager_name,
        "start_date": project.start_date.isoformat() if project.start_date else "",
        "expected_completion_date": (
            project.expected_completion_date.isoformat() if project.expected_completion_date else ""
        ),
        "end_date": project.end_date.isoformat() if project.end_date else "",
        "status": project.status,
        "notes": project.notes,
    }


def _audit_project(*, request, project: Project, action: str, before=None) -> None:
    record_audit_event(
        company=project.company,
        area=AuditArea.PROJECTS,
        action=action,
        object_type="projects.Project",
        object_id=project.reference,
        object_label=str(project),
        actor_membership=getattr(request, "company_membership", None),
        actor=request.user,
        before=before,
        after=_project_snapshot(project),
        request=request,
    )


class ProjectListView(InventoryWorkspaceMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 18

    def get_queryset(self):
        queryset = project_list(self.request.company)
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(
                Q(code__icontains=query)
                | Q(name__icontains=query)
                | Q(client_name__icontains=query)
                | Q(location__icontains=query)
                | Q(manager_name__icontains=query)
            )
        if status in Project.Status.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("code")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="projects",
            page_title="Projects",
            page_subtitle="One project master shared by Inventory and Rental Manpower.",
            status_choices=Project.Status.choices,
            current_status=self.request.GET.get("status", ""),
            search_query=self.request.GET.get("q", ""),
        )
        return context


class ProjectCreateView(InventoryWorkspaceMixin, CreateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    success_url = reverse_lazy("projects:list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.request.company
        return kwargs

    def form_valid(self, form):
        form.instance.company = self.request.company
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        _audit_project(request=self.request, project=self.object, action="project.created")
        messages.success(self.request, f"Project {self.object.code} was created.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="projects",
            page_title="Add project",
            page_subtitle="Create the shared project once, then use it across Inventory and Payroll.",
            submit_label="Create project",
        )
        return context


class ProjectUpdateView(InventoryWorkspaceMixin, UpdateView):
    model = Project
    form_class = ProjectForm
    template_name = "projects/project_form.html"
    slug_field = "code"
    slug_url_kwarg = "code"

    def get_queryset(self):
        return Project.objects.for_company(self.request.company).filter(deleted_at__isnull=True)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["company"] = self.request.company
        return kwargs

    def form_valid(self, form):
        before = _project_snapshot(
            Project.objects.for_company(self.request.company).get(pk=form.instance.pk)
        )
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        _audit_project(
            request=self.request,
            project=self.object,
            action="project.updated",
            before=before,
        )
        messages.success(self.request, f"Project {self.object.code} was updated.")
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"code": self.object.code})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="project-detail",
            page_title="Edit project",
            page_subtitle=f"Update {self.object.code} without changing its Inventory or Payroll identity.",
            submit_label="Save changes",
        )
        return context


class ProjectStatusView(InventoryWorkspaceMixin, View):
    def post(self, request, code):
        project = get_object_or_404(Project.objects.for_company(request.company), code=code, deleted_at__isnull=True)
        action = request.POST.get("action", "").strip()
        target = {
            "hold": Project.Status.ON_HOLD,
            "archive": Project.Status.ARCHIVED,
            "complete": Project.Status.COMPLETED,
            "reactivate": Project.Status.ACTIVE,
        }.get(action)
        if not target:
            messages.error(request, "Choose a valid project lifecycle action.")
            return redirect("projects:detail", code=project.code)
        before = _project_snapshot(project)
        project.status = target
        if target == Project.Status.ACTIVE:
            # Reopening a completed project starts a new live lifecycle. Expected completion
            # remains planning data; the prior actual end date is retained in the audit event.
            project.end_date = None
        project.updated_by = request.user
        try:
            project.save()
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            _audit_project(
                request=request,
                project=project,
                action="project.status_changed",
                before=before,
            )
            messages.success(
                request,
                f"Project {project.code} was "
                f"{'reactivated' if target == Project.Status.ACTIVE else project.get_status_display().lower()}.",
            )
        return redirect("projects:detail", code=project.code)


class ProjectDeleteView(InventoryAdminRequiredMixin, View):
    template_name = "inventory/delete_confirm.html"

    def _context(self, project):
        stock = project.stock_items.all()
        rental_assignments = project.rental_assignments.all() if hasattr(project, "rental_assignments") else ()
        rental_count = rental_assignments.count() if hasattr(rental_assignments, "count") else 0
        open_rental_count = (
            rental_assignments.filter(cancelled_at__isnull=True, effective_to__isnull=True).count()
            if hasattr(rental_assignments, "filter") else 0
        )
        return {
            "page_key": "projects",
            "page_title": "Move project to Trash",
            "page_subtitle": "Review the project-wide effect before continuing.",
            "record_label": str(project),
            "record_type": "Project",
            "confirmation_phrase": f"DELETE {project.code}",
            "retention_days": TRASH_RETENTION_DAYS,
            "cancel_url": reverse("projects:detail", kwargs={"code": project.code}),
            "effects": (
                f"Stock records hidden with this project: {stock.count()}",
                f"Current quantity-bearing records: {stock.filter(current_quantity__gt=0).count()}",
                f"Rental assignment history retained: {rental_count} ({open_rental_count} open)",
                (
                    "Protected activity entries retained: "
                    f"{sum(item.movements.count() for item in stock)}"
                ),
                (
                    "The project and its inventory disappear from search, activity, "
                    "alerts, and totals."
                ),
                "The project and linked inventory return together if restored within 30 days.",
            ),
        }

    def get(self, request, code):
        project = get_object_or_404(Project.objects.for_company(request.company), code=code, deleted_at__isnull=True)
        return render(request, self.template_name, self._context(project))

    def post(self, request, code):
        project = get_object_or_404(Project.objects.for_company(request.company), code=code, deleted_at__isnull=True)
        context = self._context(project)
        if hasattr(project, "rental_assignments") and project.rental_assignments.filter(
            cancelled_at__isnull=True, effective_to__isnull=True
        ).exists():
            context.update(
                form_error="Release, transfer, or cancel every open Rental Manpower assignment before moving this shared project to Trash.",
                reason=request.POST.get("reason", ""),
            )
            return render(request, self.template_name, context, status=409)
        if (
            request.POST.get("confirmation", "").strip() != context["confirmation_phrase"]
            or not request.POST.get("acknowledge")
            or not request.POST.get("reason", "").strip()
        ):
            context.update(
                form_error="Enter the exact phrase, a reason, and confirm the effect.",
                reason=request.POST.get("reason", ""),
            )
            return render(request, self.template_name, context, status=400)
        before = _project_snapshot(project)
        move_to_trash(project, user=request.user, reason=request.POST["reason"])
        _audit_project(
            request=request,
            project=project,
            action="project.moved_to_trash",
            before=before,
        )
        messages.success(request, f"Project {code} was moved to Trash for 30 days.")
        return redirect("projects:list")


class ProjectDetailView(InventoryWorkspaceMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"
    slug_field = "code"
    slug_url_kwarg = "code"

    def get_queryset(self):
        return project_list(self.request.company)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stock_items = (
            self.object.stock_items.filter(deleted_at__isnull=True)
            .select_related("unit")
            .order_by("material_name", "supplier_name")
        )
        query = self.request.GET.get("q", "").strip()
        stock_status = self.request.GET.get("stock_status", "").strip()
        record_status = self.request.GET.get("record_status", "active").strip()
        if record_status == StockItem.Status.ARCHIVED:
            stock_items = stock_items.filter(status=StockItem.Status.ARCHIVED)
        elif record_status == "all":
            pass
        else:
            record_status = StockItem.Status.ACTIVE
            stock_items = stock_items.filter(status=StockItem.Status.ACTIVE)
        stock_items = apply_stock_search(stock_items, query)
        if stock_status == "in":
            stock_items = stock_items.filter(current_quantity__gt=0).exclude(
                minimum_quantity__gt=0,
                current_quantity__lte=F("minimum_quantity"),
            )
        elif stock_status == "low":
            stock_items = stock_items.filter(
                minimum_quantity__gt=0,
                current_quantity__gt=0,
                current_quantity__lte=F("minimum_quantity"),
            )
        elif stock_status == "out":
            stock_items = stock_items.filter(current_quantity=0)
        paginator = Paginator(stock_items, 50)
        stock_page = paginator.get_page(self.request.GET.get("page"))
        all_project_items = self.object.stock_items.all()
        project_movements = stock_movements(self.request.company).filter(stock_item__project=self.object)
        context.update(
            page_key="project-detail",
            page_title=self.object.name,
            page_subtitle=f"Project inventory for {self.object.code}.",
            stock_items=stock_page.object_list,
            page_obj=stock_page,
            paginator=paginator,
            is_paginated=stock_page.has_other_pages(),
            search_query=query,
            current_stock_status=stock_status,
            current_record_status=record_status,
            active_stock_count=all_project_items.filter(status=StockItem.Status.ACTIVE).count(),
            out_of_stock_count=all_project_items.filter(
                status=StockItem.Status.ACTIVE, current_quantity=0
            ).count(),
            movement_count=project_movements.count(),
            recent_movements=project_movements[:6],
            project_source_query=self._source_query(),
            can_hold_project=self.object.status == Project.Status.ACTIVE,
            can_archive_project=(
                self.object.status in {Project.Status.ACTIVE, Project.Status.ON_HOLD}
                and not all_project_items.filter(current_quantity__gt=0).exists()
            ),
            can_complete_project=(
                self.object.status in {Project.Status.ACTIVE, Project.Status.ON_HOLD}
                and self.object.end_date is not None
                and not all_project_items.filter(current_quantity__gt=0).exists()
            ),
            needs_completion_date=(
                self.object.status in {Project.Status.ACTIVE, Project.Status.ON_HOLD}
                and self.object.end_date is None
                and not all_project_items.filter(current_quantity__gt=0).exists()
            ),
            has_stock_to_closeout=(
                self.object.status == Project.Status.ACTIVE
                and all_project_items.filter(current_quantity__gt=0).exists()
            ),
        )
        return context

    def _source_query(self):
        query = self.request.GET.copy()
        query.pop("page", None)
        return query.urlencode()
