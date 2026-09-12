from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SESCCO MS Administration"
admin.site.site_title = "SESCCO MS"
admin.site.index_title = "Management System"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.internal_payroll.urls")),
    path("", include("apps.rental_manpower.urls")),
    path("", include("apps.documents.urls")),
    path("", include(("apps.core.api_urls", "platform_api"), namespace="platform_api")),
    path("", include("apps.accounts.urls")),
    path("app/", include("apps.core.urls")),
    path("app/projects/", include("apps.projects.urls")),
    path("app/", include("apps.inventory.urls")),
    path("app/", include("apps.explorer.urls")),
    path("app/", include("apps.data_exchange.urls")),
]

