from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from .forms import InventoryAuthenticationForm


class InventoryLoginView(LoginView):
    authentication_form = InventoryAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True


def home_redirect(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    if request.user.is_inventory_admin:
        return redirect("admin:index")
    return redirect("core:dashboard")


@require_POST
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("accounts:login")
