from django.urls import path

from .views import InventoryLoginView, home_redirect, logout_view

app_name = "accounts"
urlpatterns = [
    path("", home_redirect, name="home"),
    path("login/", InventoryLoginView.as_view(), name="login"),
    path("logout/", logout_view, name="logout"),
]
