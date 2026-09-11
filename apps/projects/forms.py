from django import forms

from apps.core.forms import StyledModelForm

from .models import Project


class ProjectForm(StyledModelForm):
    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company or getattr(self.instance, "company", None)
        self.fields["end_date"].widget.attrs.update(
            {
                "data-required-when-name": "status",
                "data-required-when-value": Project.Status.COMPLETED,
            }
        )

    class Meta:
        model = Project
        fields = (
            "code",
            "name",
            "client_name",
            "location",
            "start_date",
            "expected_completion_date",
            "end_date",
            "manager_name",
            "status",
            "notes",
        )
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "expected_completion_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_code(self) -> str:
        code = self.cleaned_data["code"].strip().upper()
        if self.company is not None:
            duplicate = Project.objects.for_company(self.company).filter(code=code)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError("A project with this code already exists in this company.")
        return code

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get("status")
        start_date = cleaned.get("start_date")
        expected_completion_date = cleaned.get("expected_completion_date")
        end_date = cleaned.get("end_date")
        if start_date and expected_completion_date and expected_completion_date < start_date:
            self.add_error("expected_completion_date", "Expected completion cannot be before the start date.")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "Actual end date cannot be before the start date.")
        if status == Project.Status.COMPLETED and not end_date:
            self.add_error("end_date", "Set the actual end date before completing the project.")
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
