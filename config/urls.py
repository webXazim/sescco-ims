from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("app/", include("apps.core.urls")),
    path("app/projects/", include("apps.projects.urls")),
    path("app/", include("apps.inventory.urls")),
    path("app/", include("apps.explorer.urls")),
    path("app/", include("apps.data_exchange.urls")),
]

