"""Explicit project-scoped operational forms (never accept client company IDs)."""
from decimal import Decimal

from django import forms
from django.db import models

from .models import PulseTask, PulseWorkCategory, PulseProjectTeamMember


class PulseCategoryForm(forms.ModelForm):
    class Meta:
        model = PulseWorkCategory
        fields = ("name", "description", "sort_order", "progress_weight")
        widgets = {"description": forms.Textarea(attrs={"rows": 2}),
                   "sort_order": forms.NumberInput(attrs={"min": 0}),
                   "progress_weight": forms.NumberInput(attrs={"min": 0.01, "step": 0.01})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["progress_weight"].required = False

    def clean_progress_weight(self):
        value = self.cleaned_data.get("progress_weight")
        return value if value is not None else (self.instance.progress_weight or Decimal("1.00"))


class PulseTaskForm(forms.ModelForm):
    class Meta:
        model = PulseTask
        fields = ("category", "title", "description", "assigned_to", "priority",
                  "status", "planned_start", "due_date", "sort_order", "progress_weight")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "planned_start": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "due_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "sort_order": forms.NumberInput(attrs={"min": 0}),
            "progress_weight": forms.NumberInput(attrs={"min": 0.01, "step": 0.01}),
        }

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["progress_weight"].required = False
        self.fields["category"].queryset = PulseWorkCategory.objects.filter(
            project=project, archived_at__isnull=True
        )
        # U02 assignments do not grant access themselves; recheck on save.
        eligible = (PulseProjectTeamMember.objects.filter(project=project, is_active=True)
                    .select_related("membership__user", "membership__access_profile", "project"))
        from apps.accounts.access_policy import membership_has_permission
        from apps.accounts.access_catalog import AccessPermission
        eligible_membership_ids = [assignment.membership_id for assignment in eligible
            if assignment.has_project_access and membership_has_permission(
                assignment.membership, AccessPermission.PULSE_TASKS_VIEW)]
        from apps.accounts.models import CompanyMembership
        self.fields["assigned_to"].queryset = (CompanyMembership.objects.filter(
            pk__in=eligible_membership_ids, company=project.company,
            is_active=True, user__is_active=True,
        ).select_related("user").order_by("user__username"))
        self.fields["assigned_to"].required = False
        self.fields["assigned_to"].label_from_instance = lambda member: member.user.display_name
        self.fields["assigned_to"].empty_label = "Unassigned"
        self.fields["category"].empty_label = "Choose work category"

    def clean_progress_weight(self):
        value = self.cleaned_data.get("progress_weight")
        return value if value is not None else (self.instance.progress_weight or Decimal("1.00"))

    def clean(self):
        data = super().clean()
        # ModelForm validates the model before our save_task service runs. Keep
        # its validation consistent with the status-driven percentage rule.
        status = data.get("status")
        if status == PulseTask.Status.COMPLETED:
            self.instance.progress_percent = 100
        elif status == PulseTask.Status.NOT_STARTED or (
            status and self.instance.progress_percent == 100
        ):
            self.instance.progress_percent = 0
        return data


class PulseProgressForm(forms.Form):
    progress_percent = forms.IntegerField(
        label="Completion (%)", min_value=0, max_value=100,
        widget=forms.NumberInput(attrs={"min": 0, "max": 100, "step": 1}),
    )
    status = forms.ChoiceField(choices=PulseTask.Status.choices)
    note = forms.CharField(
        required=False, max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Describe the work completed or reason for delay"}),
    )

    def clean(self):
        data = super().clean()
        value, status = data.get("progress_percent"), data.get("status")
        if value is None or status is None:
            return data
        if (status == PulseTask.Status.COMPLETED and value != 100) or (value == 100 and status != PulseTask.Status.COMPLETED):
            self.add_error("progress_percent", "100% progress must use Completed status; Completed requires 100%.")
        if status == PulseTask.Status.NOT_STARTED and value != 0:
            self.add_error("status", "Not Started requires 0% completion.")
        return data



from .models import PulseExpenseCategory, PulseExpenseEntry


class PulseExpenseCategoryForm(forms.ModelForm):
    class Meta:
        model = PulseExpenseCategory
        fields = ("name", "description", "sort_order")
        widgets = {"description": forms.Textarea(attrs={"rows": 2}),
                   "sort_order": forms.NumberInput(attrs={"min": 0})}


class PulseExpenseForm(forms.ModelForm):
    class Meta:
        model = PulseExpenseEntry
        fields = ("expense_category", "description", "amount", "expense_date",
                  "supplier_name", "reference", "notes")
        widgets = {"expense_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
                   "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01"}),
                   "notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, project, **kwargs):
        super().__init__(*args, **kwargs)
        query = PulseExpenseCategory.objects.filter(project=project, archived_at__isnull=True)
        if self.instance.pk:
            query = PulseExpenseCategory.objects.filter(project=project).filter(
                models.Q(archived_at__isnull=True) | models.Q(pk=self.instance.expense_category_id)
            )
        self.fields["expense_category"].queryset = query.order_by("sort_order", "name")
        self.fields["expense_category"].empty_label = "Choose an expense category"


from .models import PulseExpensePayment


class PulseExpensePaymentForm(forms.ModelForm):
    class Meta:
        model = PulseExpensePayment
        fields = ("amount", "paid_on", "method", "reference", "remarks")
        widgets = {
            "amount": forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
            "paid_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }


class PulseBudgetProposalForm(forms.Form):
    amount = forms.DecimalField(
        label="Proposed budget (SAR)", max_digits=14, decimal_places=2,
        min_value=Decimal("0.00"), max_value=Decimal("999999999999.99"),
        widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        help_text="Entire approved category cost allowance, not an increment or expense.",
    )
    reason = forms.CharField(
        label="Reason / basis", max_length=500,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Required for the initial budget and every revision.",
    )


class PulseContractForm(forms.Form):
    amount = forms.DecimalField(label="Complete base contract value (SAR)", max_digits=14, decimal_places=2,
        min_value=Decimal("0.00"), widget=forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        help_text="Entire revised base contract, not an additional payment or variation.")
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))


class PulseVariationForm(forms.Form):
    description = forms.CharField(max_length=220)
    reference = forms.CharField(max_length=100, required=False)
    amount = forms.DecimalField(label="Change in contract value (SAR)", max_digits=14, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01"}),
        help_text="Use negative amounts for deductions / omissions.")
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))

    def clean_amount(self):
        value = self.cleaned_data["amount"]
        if value == 0:
            raise forms.ValidationError("Variation cannot be zero.")
        return value


class PulseForecastForm(forms.Form):
    remaining_cost = forms.DecimalField(label="Estimated remaining cost (SAR)", max_digits=14, decimal_places=2,
        min_value=Decimal("0.00"), widget=forms.NumberInput(attrs={"min": "0", "step": "0.01"}),
        help_text="Only costs still expected to be incurred. Already-approved expenses are added automatically.")
    as_of_date = forms.DateField(label="Estimate as of", widget=forms.DateInput(attrs={"type":"date"}, format="%Y-%m-%d"))
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 3}))
