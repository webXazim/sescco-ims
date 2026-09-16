from __future__ import annotations

from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import InventoryAuthenticationForm, SesccoPasswordChangeForm
from .access_catalog import AccessPermission
from .permissions import access_permission_required
from .modules import PlatformModule, membership_can_module, module_from_path, module_home_name
from .services import activate_company
from .security import SESSION_SECURITY_VERSION_KEY
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event


@login_required
@access_permission_required(AccessPermission.ACCESS_USERS_VIEW)
def administration_view(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "accounts/administration.html",
        {
            "page_key": "administration-users",
            "page_title": "User Management",
            "page_subtitle": "Company users, access profiles and operational scopes.",
        },
    )


class InventoryLoginView(LoginView):
    authentication_form = InventoryAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


@login_required
def change_password_view(request: HttpRequest) -> HttpResponse:
    form = SesccoPasswordChangeForm(user=request.user, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.credentials_updated_at = timezone.now()
        user.security_version = int(user.security_version) + 1
        user.save(update_fields=("must_change_password", "credentials_updated_at", "security_version", "is_staff"))
        update_session_auth_hash(request, user)
        request.session[SESSION_SECURITY_VERSION_KEY] = int(user.security_version)
        membership = getattr(request, "company_membership", None)
        company = getattr(request, "company", None)
        if membership is not None and company is not None:
            record_audit_event(
                company=company,
                area=AuditArea.ACCESS,
                action="access.user.password_changed",
                object_type="accounts.User",
                object_id=user.pk,
                object_label=user.display_name,
                actor_membership=membership,
                after={"mustChangePassword": False, "credentialsUpdatedAt": user.credentials_updated_at.isoformat()},
                metadata={"sessions_rotated": True},
                request=request,
            )
        return redirect("accounts:home")
    return render(
        request,
        "registration/change_password.html",
        {"form": form, "mandatory": bool(request.user.must_change_password)},
    )


def home_redirect(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    membership = getattr(request, "company_membership", None)
    if membership_can_module(membership, PlatformModule.INVENTORY):
        return redirect(module_home_name(PlatformModule.INVENTORY))
    if membership_can_module(membership, PlatformModule.PAYROLL):
        return redirect(module_home_name(PlatformModule.PAYROLL))
    if membership_can_module(membership, PlatformModule.SOURCING):
        return redirect(module_home_name(PlatformModule.SOURCING))
    if membership_can_module(membership, PlatformModule.ADMINISTRATION):
        return redirect(module_home_name(PlatformModule.ADMINISTRATION))
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
