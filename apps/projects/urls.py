from django.urls import path

from .views import ProjectCreateView, ProjectDetailView, ProjectListView, ProjectUpdateView

app_name = "projects"

urlpatterns = [
    path("", ProjectListView.as_view(), name="list"),
    path("new/", ProjectCreateView.as_view(), name="create"),
    path("<slug:code>/", ProjectDetailView.as_view(), name="detail"),
    path("<slug:code>/edit/", ProjectUpdateView.as_view(), name="edit"),
]
