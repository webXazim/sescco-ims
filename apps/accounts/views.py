from __future__ import annotations

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import InventoryAuthenticationForm
from .modules import PlatformModule, membership_can_module, module_from_path, module_home_name
from .services import activate_company


class InventoryLoginView(LoginView):
    authentication_form = InventoryAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


def home_redirect(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    membership = getattr(request, "company_membership", None)
    if membership_can_module(membership, PlatformModule.INVENTORY):
        return redirect(module_home_name(PlatformModule.INVENTORY))
    if membership_can_module(membership, PlatformModule.PAYROLL):
        return redirect(module_home_name(PlatformModule.PAYROLL))
    if request.user.is_superuser:
        return redirect("admin:index")
    return redirect("accounts:login")


@login_required
@require_POST
def activate_company_view(request: HttpRequest, company_id) -> HttpResponse:
    membership = activate_company(request, company_id)
    requested_module = request.POST.get("module", "").strip()
    if requested_module:
        try:
            module = PlatformModule(requested_module)
        except ValueError:
            module = None
        if module is not None and membership_can_module(membership, module):
            return redirect(reverse(module_home_name(module)))

    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        requested_module = module_from_path(next_url)
        if requested_module is None or membership_can_module(membership, requested_module):
            return redirect(next_url)
    return redirect(reverse("accounts:home"))


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("accounts:login")
