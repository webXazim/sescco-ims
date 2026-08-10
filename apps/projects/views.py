from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.core.access import InventoryAdminRequiredMixin, InventoryWorkspaceMixin
from apps.inventory.models import StockItem
from apps.inventory.selectors import apply_stock_search, stock_movements

from .forms import ProjectForm
from .models import Project
from .selectors import project_list


class ProjectListView(InventoryWorkspaceMixin, ListView):
    model = Project
    template_name = "projects/project_list.html"
    context_object_name = "projects"
    paginate_by = 18

    def get_queryset(self):
        queryset = project_list()
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "").strip()
        if query:
            queryset = queryset.filter(
                Q(code__icontains=query)
                | Q(name__icontains=query)
                | Q(client_name__icontains=query)
                | Q(location__icontains=query)
            )
        if status in Project.Status.values:
            queryset = queryset.filter(status=status)
        return queryset.order_by("code")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="projects",
            page_title="Projects",
            page_subtitle="Project tags keep purchased and used stock separated.",
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

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Project {self.object.code} was created.")
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="projects",
            page_title="Add project",
            page_subtitle="Create a project tag before assigning stock.",
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
        return Project.objects.all()

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        response = super().form_valid(form)
        messages.success(self.request, f"Project {self.object.code} was updated.")
        return response

    def get_success_url(self):
        return reverse("projects:detail", kwargs={"code": self.object.code})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            page_key="project-detail",
            page_title="Edit project",
            page_subtitle=f"Update {self.object.code} without changing its stock history.",
            submit_label="Save changes",
        )
        return context


class ProjectStatusView(InventoryWorkspaceMixin, View):
    def post(self, request, code):
        project = get_object_or_404(Project, code=code)
        action = request.POST.get("action", "").strip()
        target = {
            "archive": Project.Status.ARCHIVED,
            "reactivate": Project.Status.ACTIVE,
        }.get(action)
        if not target:
            messages.error(request, "Choose a valid project lifecycle action.")
            return redirect("projects:detail", code=project.code)
        project.status = target
        project.updated_by = request.user
        try:
            project.save()
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
        else:
            messages.success(
                request,
                f"Project {project.code} was "
                f"{'reactivated' if target == Project.Status.ACTIVE else 'archived'}.",
            )
        return redirect("projects:detail", code=project.code)


class ProjectDeleteView(InventoryAdminRequiredMixin, View):
    def post(self, request, code):
        project = get_object_or_404(Project, code=code)
        if project.stock_items.exists() or project.import_jobs.exists():
            messages.error(
                request,
                "This project has inventory or import history. Archive it instead of deleting it.",
            )
            return redirect("projects:detail", code=project.code)
        try:
            project.delete()
        except ProtectedError:
            messages.error(request, "This project is still referenced and cannot be deleted.")
            return redirect("projects:detail", code=project.code)
        messages.success(request, f"Unused project {code} was permanently deleted.")
        return redirect("projects:list")


class ProjectDetailView(InventoryWorkspaceMixin, DetailView):
    model = Project
    template_name = "projects/project_detail.html"
    context_object_name = "project"
    slug_field = "code"
    slug_url_kwarg = "code"

    def get_queryset(self):
        return project_list()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        stock_items = self.object.stock_items.select_related("unit").order_by(
            "material_name", "supplier_name"
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
        project_movements = stock_movements().filter(stock_item__project=self.object)
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
            active_stock_count=all_project_items.filter(
                status=StockItem.Status.ACTIVE
            ).count(),
            out_of_stock_count=all_project_items.filter(
                status=StockItem.Status.ACTIVE, current_quantity=0
            ).count(),
            movement_count=project_movements.count(),
            recent_movements=project_movements[:6],
            project_source_query=self._source_query(),
            can_archive_project=(
                self.object.status == Project.Status.ACTIVE
                and not all_project_items.filter(current_quantity__gt=0).exists()
            ),
        )
        return context

    def _source_query(self):
        query = self.request.GET.copy()
        query.pop("page", None)
        return query.urlencode()
