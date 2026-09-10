from django.urls import path

from .views import InventoryLoginView, activate_company_view, home_redirect, logout_view

app_name = "accounts"
urlpatterns = [
    path("", home_redirect, name="home"),
    path("login/", InventoryLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
    path("company/<uuid:company_id>/activate/", activate_company_view, name="activate-company"),
]
