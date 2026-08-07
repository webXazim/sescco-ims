from django.urls import path

from .views import (
    SavedViewCreateView,
    SavedViewDeleteView,
    SavedViewListView,
    SavedViewOpenView,
    SavedViewRenameView,
)

app_name = "explorer"

urlpatterns = [
    path("saved-views/", SavedViewListView.as_view(), name="saved_views"),
    path("saved-views/create/", SavedViewCreateView.as_view(), name="saved_view_create"),
    path("saved-views/<int:pk>/", SavedViewOpenView.as_view(), name="saved_view_open"),
    path("saved-views/<int:pk>/rename/", SavedViewRenameView.as_view(), name="saved_view_rename"),
    path("saved-views/<int:pk>/delete/", SavedViewDeleteView.as_view(), name="saved_view_delete"),
]
