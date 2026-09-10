from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import money_field, rate_field
from apps.core.models import CompanyOwnedModel


class SalaryComponentCategory(models.TextChoices):
    EARNING = "earning", "Earning"
    DEDUCTION = "deduction", "Deduction"


class SalaryComponentRecurrence(models.TextChoices):
    RECURRING = "recurring", "Recurring"
    VARIABLE = "variable", "Variable"


class SalaryComponentCalculation(models.TextChoices):
    FIXED_AMOUNT = "fixed_amount", "Fixed Amount"
    MANUAL_AMOUNT = "manual_amount", "Manual Amount"


class WPSMapping(models.TextChoices):
    BASIC_SALARY = "basic_salary", "Basic Salary"
    HOUSING_ALLOWANCE = "housing_allowance", "Housing Allowance"
    OTHER_EARNINGS = "other_earnings", "Other Earnings"
    DEDUCTIONS = "deductions", "Deductions"
    NOT_MAPPED = "not_mapped", "Not mapped"


class SalaryComponent(CompanyOwnedModel):
    """Reusable internal-payroll earning/deduction definition.

    Employee structures snapshot the component semantics, so later edits only affect future
    assignments and never reinterpret an already-effective salary structure.
    """

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=160)
    category = models.CharField(max_length=20, choices=SalaryComponentCategory.choices)
    recurrence = models.CharField(max_length=20, choices=SalaryComponentRecurrence.choices)
    calculation = models.CharField(max_length=30, choices=SalaryComponentCalculation.choices)
    wps_mapping = models.CharField(max_length=30, choices=WPSMapping.choices, default=WPSMapping.NOT_MAPPED)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "internal_salary_component"
        ordering = ("category", "code", "name")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="int_sal_comp_company_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="int_sal_comp_company_name_uniq"),
            models.CheckConstraint(
                condition=Q(category__in=[value for value, _label in SalaryComponentCategory.choices]),
                name="int_sal_comp_category_valid",
            ),
            models.CheckConstraint(
                condition=Q(recurrence__in=[value for value, _label in SalaryComponentRecurrence.choices]),
                name="int_sal_comp_recur_valid",
            ),
            models.CheckConstraint(
                condition=Q(calculation__in=[value for value, _label in SalaryComponentCalculation.choices]),
                name="int_sal_comp_calc_valid",
            ),
            models.CheckConstraint(
                condition=Q(wps_mapping__in=[value for value, _label in WPSMapping.choices]),
                name="int_sal_comp_wps_valid",
            ),
            models.UniqueConstraint(
                fields=("company",),
                condition=Q(wps_mapping=WPSMapping.BASIC_SALARY, is_active=True),
                name="int_sal_comp_one_active_basic",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "category"), name="int_sal_comp_active_idx"),
            models.Index(fields=("company", "wps_mapping"), name="int_sal_comp_wps_idx"),
        ]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        if not self.code:
            raise ValidationError({"code": "Component code is required."})
        if not self.name:
            raise ValidationError({"name": "Component name is required."})
        if self.wps_mapping == WPSMapping.BASIC_SALARY:
            if self.category != SalaryComponentCategory.EARNING:
                raise ValidationError({"category": "Basic Salary must be an earning component."})
            if self.recurrence != SalaryComponentRecurrence.RECURRING:
                raise ValidationError({"recurrence": "Basic Salary must be recurring."})
        if self.wps_mapping == WPSMapping.HOUSING_ALLOWANCE and self.category != SalaryComponentCategory.EARNING:
            raise ValidationError({"category": "Housing Allowance mapping requires an earning component."})
        if self.wps_mapping == WPSMapping.OTHER_EARNINGS and self.category != SalaryComponentCategory.EARNING:
            raise ValidationError({"category": "Other Earnings mapping requires an earning component."})
        if self.wps_mapping == WPSMapping.DEDUCTIONS and self.category != SalaryComponentCategory.DEDUCTION:
            raise ValidationError({"category": "Deductions mapping requires a deduction component."})

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class OvertimePolicy(CompanyOwnedModel):
    """Named overtime formula reusable by future employee salary structures."""

    code = models.CharField(max_length=30)
    name = models.CharField(max_length=160)
    base_component = models.ForeignKey(
        SalaryComponent,
        on_delete=models.PROTECT,
        related_name="overtime_policies",
    )
    divisor = rate_field()
    multiplier = rate_field()
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "internal_overtime_policy"
        ordering = ("code", "name")
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="int_ot_pol_company_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="int_ot_pol_company_name_uniq"),
            models.CheckConstraint(condition=Q(divisor__gt=0), name="int_ot_pol_divisor_positive"),
            models.CheckConstraint(condition=Q(multiplier__gt=0), name="int_ot_pol_multiplier_positive"),
        ]
        indexes = [models.Index(fields=("company", "is_active", "name"), name="int_ot_policy_active_idx")]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        if not self.code:
            raise ValidationError({"code": "Overtime policy code is required."})
        if not self.name:
            raise ValidationError({"name": "Overtime policy name is required."})
        if self.divisor is None or self.divisor <= Decimal("0"):
            raise ValidationError({"divisor": "Divisor must be greater than zero."})
        if self.multiplier is None or self.multiplier <= Decimal("0"):
            raise ValidationError({"multiplier": "Multiplier must be greater than zero."})
        if self.base_component_id:
            if self.company_id and self.base_component.company_id != self.company_id:
                raise ValidationError({"base_component": "Base component must belong to the same company."})
            if self.base_component.category != SalaryComponentCategory.EARNING:
                raise ValidationError({"base_component": "Overtime must be based on an earning component."})
            if self.base_component.recurrence != SalaryComponentRecurrence.RECURRING:
                raise ValidationError({"base_component": "Overtime base component must be recurring."})

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class SalaryStructure(CompanyOwnedModel):
    """Effective-dated employee salary assignment.

    Lines and overtime formula fields are snapshots. This makes the salary assignment itself
    historically stable even when component masters or overtime policies are later changed.
    """

    employee = models.ForeignKey(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="salary_structures",
    )
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)
    overtime_policy = models.ForeignKey(
        OvertimePolicy,
        on_delete=models.PROTECT,
        related_name="salary_structures",
        null=True,
        blank=True,
    )
    overtime_policy_code = models.CharField(max_length=30, blank=True)
    overtime_policy_name = models.CharField(max_length=160, blank=True)
    overtime_base_component_code = models.CharField(max_length=30, blank=True)
    overtime_base_component_name = models.CharField(max_length=160, blank=True)
    overtime_divisor = rate_field(null=True, blank=True)
    overtime_multiplier = rate_field(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "internal_salary_structure"
        ordering = ("-effective_from", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("employee", "effective_from"), name="int_sal_struct_emp_date_uniq"),
            models.CheckConstraint(
                condition=Q(effective_to__isnull=True) | Q(effective_to__gte=models.F("effective_from")),
                name="int_sal_struct_valid_range",
            ),
            models.UniqueConstraint(
                fields=("employee",),
                condition=Q(effective_to__isnull=True),
                name="int_sal_struct_one_open",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "employee", "-effective_from"), name="int_sal_struct_emp_idx"),
            models.Index(fields=("company", "effective_from", "effective_to"), name="int_sal_struct_dates_idx"),
        ]

    def clean(self) -> None:
        self.notes = self.notes.strip()
        if self.employee_id and self.company_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValidationError({"effective_to": "Salary structure end date cannot be before its start date."})
        if self.employee_id:
            if self.effective_from < self.employee.joining_date:
                raise ValidationError({"effective_from": "Salary structure cannot start before the employee joining date."})
            if self.employee.employment_end_date and self.effective_from > self.employee.employment_end_date:
                raise ValidationError({"effective_from": "Salary structure cannot start after the employee employment end date."})
        if self.overtime_policy_id and self.company_id and self.overtime_policy.company_id != self.company_id:
            raise ValidationError({"overtime_policy": "Overtime policy must belong to the same company."})

    def __str__(self) -> str:
        return f"{self.employee} · {self.effective_from.isoformat()}"


class SalaryStructureLine(CompanyOwnedModel):
    structure = models.ForeignKey(SalaryStructure, on_delete=models.PROTECT, related_name="lines")
    component = models.ForeignKey(SalaryComponent, on_delete=models.PROTECT, related_name="salary_structure_lines")
    amount = money_field()

    component_code = models.CharField(max_length=30)
    component_name = models.CharField(max_length=160)
    component_category = models.CharField(max_length=20, choices=SalaryComponentCategory.choices)
    component_recurrence = models.CharField(max_length=20, choices=SalaryComponentRecurrence.choices)
    component_calculation = models.CharField(max_length=30, choices=SalaryComponentCalculation.choices)
    wps_mapping = models.CharField(max_length=30, choices=WPSMapping.choices)

    class Meta:
        db_table = "internal_salary_structure_line"
        ordering = ("component_category", "component_code")
        constraints = [
            models.UniqueConstraint(fields=("structure", "component"), name="int_sal_line_struct_comp_uniq"),
            models.CheckConstraint(condition=Q(amount__gte=0), name="int_sal_line_amount_nonneg"),
            models.CheckConstraint(
                condition=Q(component_category__in=[value for value, _label in SalaryComponentCategory.choices]),
                name="int_sal_line_cat_valid",
            ),
            models.CheckConstraint(
                condition=Q(component_recurrence__in=[value for value, _label in SalaryComponentRecurrence.choices]),
                name="int_sal_line_recur_valid",
            ),
            models.CheckConstraint(
                condition=Q(component_calculation__in=[value for value, _label in SalaryComponentCalculation.choices]),
                name="int_sal_line_calc_valid",
            ),
            models.CheckConstraint(
                condition=Q(wps_mapping__in=[value for value, _label in WPSMapping.choices]),
                name="int_sal_line_wps_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "structure"), name="int_sal_line_struct_idx"),
            models.Index(fields=("company", "component"), name="int_sal_line_component_idx"),
        ]

    def clean(self) -> None:
        self.component_code = self.component_code.strip().upper()
        self.component_name = self.component_name.strip()
        if self.amount is None or self.amount < Decimal("0"):
            raise ValidationError({"amount": "Salary component amount cannot be negative."})
        if self.structure_id and self.company_id and self.structure.company_id != self.company_id:
            raise ValidationError({"structure": "Salary structure must belong to the same company."})
        if self.component_id and self.company_id and self.component.company_id != self.company_id:
            raise ValidationError({"component": "Salary component must belong to the same company."})

    def __str__(self) -> str:
        return f"{self.structure} · {self.component_code}"
