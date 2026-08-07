from django import forms

from apps.core.forms import StyledModelForm

from .models import Project


class ProjectForm(StyledModelForm):
    class Meta:
        model = Project
        fields = (
            "code",
            "name",
            "client_name",
            "location",
            "start_date",
            "expected_completion_date",
            "status",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expected_completion_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_code(self) -> str:
        return self.cleaned_data["code"].strip().upper()

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        if (
            self.instance.pk
            and status in {Project.Status.COMPLETED, Project.Status.ARCHIVED}
            and self.instance.status != status
            and self.instance.stock_items.filter(current_quantity__gt=0).exists()
        ):
            self.add_error(
                "status",
                "A project can be completed or archived only after every stock balance is zero.",
            )
        return cleaned
