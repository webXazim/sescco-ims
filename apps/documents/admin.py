from django.contrib import admin

from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace

from .models import BusinessDocument, DocumentWorkspace


@admin.register(BusinessDocument)
class BusinessDocumentAdmin(admin.ModelAdmin):
    """Tenant-scoped, immutable payroll document snapshots.

    Documents are finalized only through audited domain services. Django admin is intentionally
    read-only and only exposes documents from the request's active company/workspaces.
    """

    list_display = (
        "document_number",
        "document_type",
        "workspace",
        "period_start",
        "entity_name",
        "finalized_at",
    )
    list_filter = ("workspace", "document_type", "period_start")
    search_fields = (
        "document_number",
        "entity_reference",
        "entity_name",
        "source_reference",
        "external_reference",
    )
    readonly_fields = tuple(field.name for field in BusinessDocument._meta.fields)
    list_select_related = ("company", "finalized_by")

    def _membership(self, request):
        return getattr(request, "company_membership", None)

    def has_module_permission(self, request):
        membership = self._membership(request)
        return membership_can_workspace(membership, Workspace.INTERNAL) or membership_can_workspace(
            membership, Workspace.RENTAL
        )

    def has_view_permission(self, request, obj=None):
        membership = self._membership(request)
        if membership is None:
            return False
        if obj is None:
            return self.has_module_permission(request)
        company = getattr(request, "company", None)
        if company is None or obj.company_id != company.pk:
            return False
        workspace = Workspace.INTERNAL if obj.workspace == DocumentWorkspace.INTERNAL else Workspace.RENTAL
        return membership_can_workspace(membership, workspace)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        company = getattr(request, "company", None)
        membership = self._membership(request)
        if company is None or membership is None:
            return qs.none()
        allowed = []
        if membership_can_workspace(membership, Workspace.INTERNAL):
            allowed.append(DocumentWorkspace.INTERNAL)
        if membership_can_workspace(membership, Workspace.RENTAL):
            allowed.append(DocumentWorkspace.RENTAL)
        return qs.filter(company=company, workspace__in=allowed)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
