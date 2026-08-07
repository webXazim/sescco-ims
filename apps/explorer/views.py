from __future__ import annotations

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.core.access import InventoryWorkspaceMixin

from .filtering import build_query_url
from .forms import SavedViewCreateForm, SavedViewRenameForm
from .models import SavedView
from .services import clean_saved_params, create_saved_view


VIEW_URL_NAMES = {
    SavedView.ViewType.INVENTORY: "inventory:list",
    SavedView.ViewType.ACTIVITY: "core:activity",
    SavedView.ViewType.LOW_STOCK: "inventory:low_stock",
}


def saved_view_target(saved_view: SavedView) -> str:
    name = VIEW_URL_NAMES.get(saved_view.view_type)
    if not name:
        raise Http404("Unsupported saved view type.")
    return build_query_url(reverse(name), saved_view.query_params)


class SavedViewListView(InventoryWorkspaceMixin, View):
    template_name = "explorer/saved_view_list.html"

    def get(self, request):
        views = SavedView.objects.filter(owner=request.user)
        query = request.GET.get("q", "").strip()
        if query:
            views = views.filter(
                Q(name__icontains=query) | Q(view_type__icontains=query)
            )
        return render(
            request,
            self.template_name,
            {
                "page_key": "saved-views",
                "page_title": "Saved views",
                "page_subtitle": "Reusable inventory and activity filters for daily work.",
                "inventory_views": views.filter(view_type=SavedView.ViewType.INVENTORY),
                "activity_views": views.filter(view_type=SavedView.ViewType.ACTIVITY),
                "low_stock_views": views.filter(view_type=SavedView.ViewType.LOW_STOCK),
                "search_query": query,
            },
        )


class SavedViewCreateView(InventoryWorkspaceMixin, View):
    def post(self, request):
        view_type = request.POST.get("view_type", "")
        form = SavedViewCreateForm(request.POST)
        source_query = request.POST.get("source_query", "")
        from django.http import QueryDict

        query = QueryDict(source_query)
        if view_type not in VIEW_URL_NAMES:
            messages.error(request, "That page cannot be saved as a view.")
            return redirect("explorer:saved_views")
        if form.is_valid():
            try:
                saved = create_saved_view(
                    owner=request.user,
                    name=form.cleaned_data["name"],
                    view_type=view_type,
                    query=query,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, f'View “{saved.name}” was saved.')
                return redirect(saved_view_target(saved))
        else:
            messages.error(request, "Enter a valid saved-view name.")
        safe_params = clean_saved_params(view_type, query)
        return redirect(build_query_url(reverse(VIEW_URL_NAMES[view_type]), safe_params))


class SavedViewOpenView(InventoryWorkspaceMixin, View):
    def get(self, request, pk):
        saved = get_object_or_404(SavedView, pk=pk, owner=request.user)
        return redirect(saved_view_target(saved))


class SavedViewRenameView(InventoryWorkspaceMixin, View):
    def post(self, request, pk):
        saved = get_object_or_404(SavedView, pk=pk, owner=request.user)
        form = SavedViewRenameForm(request.POST, instance=saved)
        if form.is_valid():
            try:
                with transaction.atomic():
                    form.save()
            except IntegrityError:
                messages.error(request, "A saved view with that name already exists.")
            else:
                messages.success(request, "Saved view was renamed.")
        else:
            messages.error(request, "Enter a valid saved-view name.")
        return redirect("explorer:saved_views")


class SavedViewDeleteView(InventoryWorkspaceMixin, View):
    def post(self, request, pk):
        saved = get_object_or_404(SavedView, pk=pk, owner=request.user)
        name = saved.name
        saved.delete()
        messages.success(request, f'View “{name}” was deleted.')
        return redirect("explorer:saved_views")
