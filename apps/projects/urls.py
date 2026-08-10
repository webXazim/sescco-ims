from django.urls import path

from .views import (
    ProjectCreateView,
    ProjectDeleteView,
    ProjectDetailView,
    ProjectListView,
    ProjectStatusView,
    ProjectUpdateView,
)

app_name = "projects"

urlpatterns = [
    path("", ProjectListView.as_view(), name="list"),
    path("new/", ProjectCreateView.as_view(), name="create"),
    path("<slug:code>/", ProjectDetailView.as_view(), name="detail"),
    path("<slug:code>/edit/", ProjectUpdateView.as_view(), name="edit"),
    path("<slug:code>/status/", ProjectStatusView.as_view(), name="status"),
    path("<slug:code>/delete/", ProjectDeleteView.as_view(), name="delete"),
]
