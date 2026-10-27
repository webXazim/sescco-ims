from django import forms

from apps.core.forms import StyledModelForm

from .models import Project


class ProjectForm(StyledModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company or getattr(self.instance, "company", None)

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
