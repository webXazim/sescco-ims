from django.urls import path

from .views import InventoryLoginView, activate_company_view, administration_view, change_password_view, home_redirect, logout_view
from .access_api import (access_audit_api, access_profile_detail_api, access_profiles_api, access_scope_lookup_api, access_user_detail_api, access_user_history_api, access_user_password_reset_api, access_user_restore_api, access_user_status_api, access_users_api)

app_name = "accounts"
urlpatterns = [
    path("app/administration/", administration_view, name="administration"),
    path("api/access/users/", access_users_api, name="access-users-api"),
    path("api/access/users/<uuid:membership_id>/", access_user_detail_api, name="access-user-detail-api"),
    path("api/access/users/<uuid:membership_id>/status/", access_user_status_api, name="access-user-status-api"),
    path("api/access/users/<uuid:membership_id>/reset-password/", access_user_password_reset_api, name="access-user-password-reset-api"),
    path("api/access/users/<uuid:membership_id>/history/", access_user_history_api, name="access-user-history-api"),
    path("api/access/users/<uuid:membership_id>/restore-access/", access_user_restore_api, name="access-user-restore-api"),
    path("api/access/audit/", access_audit_api, name="access-audit-api"),
    path("api/access/profiles/", access_profiles_api, name="access-profiles-api"),
    path("api/access/profiles/<uuid:profile_id>/", access_profile_detail_api, name="access-profile-detail-api"),
    path("api/access/scopes/lookup/", access_scope_lookup_api, name="access-scope-lookup-api"),
    path("", home_redirect, name="home"),
    path("login/", InventoryLoginView.as_view(), name="login"),
    path("account/password/change/", change_password_view, name="change-password"),
    path("logout/", logout_view, name="logout"),
    path("company/<uuid:company_id>/activate/", activate_company_view, name="activate-company"),
]
