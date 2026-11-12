from django import forms

from apps.core.forms import StyledModelForm
from apps.accounts.models import CompanyMembership
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission

from .models import Project


class ProjectForm(StyledModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company or getattr(self.instance, "company", None)
        memberships = CompanyMembership.objects.filter(
            company=self.company, is_active=True, user__is_active=True,
        ).select_related("access_profile", "user") if self.company else CompanyMembership.objects.none()
        user_ids = [m.user_id for m in memberships if membership_has_permission(m, AccessPermission.INVENTORY_STOCK_APPROVE)]
        from django.contrib.auth import get_user_model
        self.fields["inventory_manager"].queryset = get_user_model().objects.filter(pk__in=user_ids).order_by("username")
        self.fields["inventory_manager"].label = "Project inventory approver"
        self.fields["inventory_manager"].help_text = "Assign a Project Manager access profile in Administration first. Required before project receipts or transfers can be submitted."

    class Meta:
        model = Project
        fields = (
            "name",
            "client_name",
            "location",
            "start_date",
            "expected_completion_date",
            "end_date",
            "manager_name",
            "inventory_manager",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expected_completion_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean(self):
        cleaned = super().clean()
        start_date = cleaned.get("start_date")
        expected_completion_date = cleaned.get("expected_completion_date")
        end_date = cleaned.get("end_date")
        if start_date and expected_completion_date and expected_completion_date < start_date:
            self.add_error("expected_completion_date", "Expected completion cannot be before the start date.")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Actual end date cannot be before the start date.")
        return cleaned
