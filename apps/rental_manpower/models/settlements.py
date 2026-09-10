from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import hours_field, money_field, rate_field
from apps.core.models import CompanyOwnedModel
from .assignments import RentalRateType


class RentalAdjustmentType(models.TextChoices):
    ADVANCE = "advance", "Worker Advance"
    BONUS = "bonus", "Bonus"
    REIMBURSEMENT = "reimbursement", "Reimbursement"
    FINE = "fine", "Fine / Penalty"
    OTHER_EARNING = "other_earning", "Other Earning"
    OTHER_DEDUCTION = "other_deduction", "Other Deduction"


class RentalAdjustmentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    REVIEW = "review", "Review"
    APPROVED = "approved", "Approved"


class RentalAdjustmentEffect(models.TextChoices):
    EARNING = "earning", "Adds to supplier payable"
    DEDUCTION = "deduction", "Deducts from supplier payable"


EARNING_ADJUSTMENT_TYPES = {
    RentalAdjustmentType.BONUS,
    RentalAdjustmentType.REIMBURSEMENT,
    RentalAdjustmentType.OTHER_EARNING,
}


def rental_adjustment_effect(adjustment_type: str) -> str:
    return (
        RentalAdjustmentEffect.EARNING
        if adjustment_type in EARNING_ADJUSTMENT_TYPES
        else RentalAdjustmentEffect.DEDUCTION
    )


class RentalAdjustment(CompanyOwnedModel):
    """Controlled one-time rental-worker transaction attributed to one settlement period/project."""

    worker = models.ForeignKey(
        "rental_manpower.RentalWorker",
        on_delete=models.PROTECT,
        related_name="rental_settlement_adjustments",
    )
    supplier = models.ForeignKey(
        "rental_manpower.ManpowerSupplier",
        on_delete=models.PROTECT,
        related_name="rental_settlement_adjustments",
    )
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="rental_settlement_adjustments",
    )
    assignment = models.ForeignKey(
        "rental_manpower.WorkerAssignment",
        on_delete=models.PROTECT,
        related_name="rental_settlement_adjustments",
    )
    transaction_date = models.DateField()
    period_start = models.DateField(db_index=True)
    adjustment_type = models.CharField(max_length=24, choices=RentalAdjustmentType.choices)
    amount = money_field()
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(
        max_length=16,
        choices=RentalAdjustmentStatus.choices,
        default=RentalAdjustmentStatus.DRAFT,
        db_index=True,
    )

    worker_number = models.CharField(max_length=30)
    worker_name = models.CharField(max_length=200)
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)
    project_code = models.CharField(max_length=30)
    project_name = models.CharField(max_length=220)
    trade = models.CharField(max_length=120)
    rate_type = models.CharField(max_length=16, choices=RentalRateType.choices)
    rate = rate_field()

    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_rental_adjustments",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_rental_adjustments",
    )

    class Meta:
        db_table = "rental_adjustment"
        ordering = ("-transaction_date", "-created_at")
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="rntl_adj_amount_pos_chk"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in RentalAdjustmentStatus.choices]),
                name="rntl_adj_status_chk",
            ),
            models.CheckConstraint(
                condition=Q(adjustment_type__in=[value for value, _label in RentalAdjustmentType.choices]),
                name="rntl_adj_type_chk",
            ),
            models.CheckConstraint(
                condition=Q(rate_type__in=[value for value, _label in RentalRateType.choices]),
                name="rntl_adj_rate_type_chk",
            ),
            models.UniqueConstraint(
                fields=("company", "reference"),
                condition=~Q(reference=""),
                name="rntl_adj_ref_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "period_start", "status"), name="rntl_adj_period_st_idx"),
            models.Index(fields=("company", "worker", "period_start"), name="rntl_adj_worker_per_idx"),
            models.Index(fields=("company", "project", "supplier", "period_start"), name="rntl_adj_scope_per_idx"),
        ]

    def clean(self) -> None:
        self.reason = (self.reason or "").strip()
        self.reference = (self.reference or "").strip().upper()
        if not self.reason:
            raise ValidationError({"reason": "A clear adjustment reason is required."})
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Adjustment period must start on the first day of a month."})
        if self.transaction_date.year != self.period_start.year or self.transaction_date.month != self.period_start.month:
            raise ValidationError({"transaction_date": "Transaction date must fall inside the selected settlement month."})
        if self.amount is None or self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Amount must be greater than zero."})
        for field in ("worker", "supplier", "project", "assignment"):
            obj = getattr(self, field, None)
            if obj is not None and self.company_id and obj.company_id != self.company_id:
                raise ValidationError({field: f"{field.replace('_', ' ').title()} must belong to the same company."})
        if self.worker_id and self.supplier_id and self.worker.supplier_id != self.supplier_id:
            raise ValidationError({"supplier": "Supplier must match the worker's permanent supplier."})
        if self.assignment_id:
            if self.assignment.worker_id != self.worker_id or self.assignment.project_id != self.project_id:
                raise ValidationError({"assignment": "Assignment must match the worker and project."})
            if self.transaction_date < self.assignment.effective_from or (
                self.assignment.effective_to and self.transaction_date > self.assignment.effective_to
            ):
                raise ValidationError({"assignment": "Assignment is not effective on the transaction date."})


class RentalSettlementStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    CALCULATED = "calculated", "Calculated"
    REVIEW = "review", "Review"
    APPROVED = "approved", "Approved"
    PAYMENT_PROCESSING = "payment_processing", "Payment Processing"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    PAID = "paid", "Paid"
    CLOSED = "closed", "Closed"


class SupplierSettlement(CompanyOwnedModel):
    """Immutable supplier/project/month financial snapshot once approved."""

    settlement_number = models.CharField(max_length=40)
    period_start = models.DateField()
    period_end = models.DateField()
    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.PROTECT,
        related_name="rental_supplier_settlements",
    )
    supplier = models.ForeignKey(
        "rental_manpower.ManpowerSupplier",
        on_delete=models.PROTECT,
        related_name="rental_supplier_settlements",
    )
    source_timesheet = models.ForeignKey(
        "rental_manpower.RentalTimesheetPeriod",
        on_delete=models.PROTECT,
        related_name="rental_supplier_settlements",
    )
    source_timesheet_revision = models.PositiveIntegerField()
    status = models.CharField(
        max_length=24,
        choices=RentalSettlementStatus.choices,
        default=RentalSettlementStatus.DRAFT,
        db_index=True,
    )
    revision = models.PositiveIntegerField(default=0)
    calculation_version = models.PositiveSmallIntegerField(default=1)
    source_fingerprint = models.CharField(max_length=64, blank=True)
    snapshot_fingerprint = models.CharField(max_length=64, blank=True)

    project_code = models.CharField(max_length=30)
    project_name = models.CharField(max_length=220)
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)

    worker_count = models.PositiveIntegerField(default=0)
    total_regular_hours = hours_field(default=Decimal("0"))
    total_work_days = models.PositiveIntegerField(default=0)
    total_overtime_hours = hours_field(default=Decimal("0"))
    total_base = money_field(default=Decimal("0"))
    total_overtime = money_field(default=Decimal("0"))
    total_gross = money_field(default=Decimal("0"))
    total_adjustment_earnings = money_field(default=Decimal("0"))
    total_adjustment_deductions = money_field(default=Decimal("0"))
    total_net = money_field(default=Decimal("0"))

    calculated_at = models.DateTimeField(null=True, blank=True)
    calculated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="calculated_rental_settlements",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submitted_rental_settlements",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_rental_settlements",
    )
    reviewer_note = models.CharField(max_length=500, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_rental_settlements",
    )

    class Meta:
        db_table = "rental_supplier_settlement"
        ordering = ("-period_start", "project_code", "supplier_code")
        constraints = [
            models.UniqueConstraint(fields=("company", "settlement_number"), name="rntl_set_no_uniq"),
            models.UniqueConstraint(fields=("company", "project", "supplier", "period_start"), name="rntl_set_scope_uniq"),
            models.CheckConstraint(condition=Q(period_end__gte=models.F("period_start")), name="rntl_set_dates_chk"),
            models.CheckConstraint(condition=Q(source_timesheet_revision__gte=1), name="rntl_set_ts_rev_chk"),
            models.CheckConstraint(condition=Q(revision__gte=0), name="rntl_set_rev_chk"),
            models.CheckConstraint(condition=Q(calculation_version__gte=1), name="rntl_set_calc_ver_chk"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in RentalSettlementStatus.choices]),
                name="rntl_set_status_chk",
            ),
            models.CheckConstraint(condition=Q(total_regular_hours__gte=0), name="rntl_set_reg_hrs_chk"),
            models.CheckConstraint(condition=Q(total_overtime_hours__gte=0), name="rntl_set_ot_hrs_chk"),
            models.CheckConstraint(condition=Q(total_base__gte=0), name="rntl_set_base_chk"),
            models.CheckConstraint(condition=Q(total_overtime__gte=0), name="rntl_set_ot_amt_chk"),
            models.CheckConstraint(condition=Q(total_gross__gte=0), name="rntl_set_gross_chk"),
            models.CheckConstraint(condition=Q(total_adjustment_earnings__gte=0), name="rntl_set_adj_earn_chk"),
            models.CheckConstraint(condition=Q(total_adjustment_deductions__gte=0), name="rntl_set_adj_ded_chk"),
            models.CheckConstraint(condition=Q(total_net__gte=0), name="rntl_set_net_chk"),
            models.CheckConstraint(condition=Q(total_gross=models.F("total_base") + models.F("total_overtime")), name="rntl_set_gross_math_chk"),
            models.CheckConstraint(
                condition=Q(total_net=models.F("total_gross") + models.F("total_adjustment_earnings") - models.F("total_adjustment_deductions")),
                name="rntl_set_net_math_chk",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "period_start", "status"), name="rntl_set_period_st_idx"),
            models.Index(fields=("company", "supplier", "-period_start"), name="rntl_set_supplier_idx"),
            models.Index(fields=("company", "project", "-period_start"), name="rntl_set_project_idx"),
        ]

    def clean(self) -> None:
        self.settlement_number = (self.settlement_number or "").strip().upper()
        self.reviewer_note = (self.reviewer_note or "").strip()
        if not self.settlement_number:
            raise ValidationError({"settlement_number": "Settlement number is required."})
        if self.period_start.day != 1:
            raise ValidationError({"period_start": "Settlement period must start on the first day of a month."})
        if self.project_id and self.company_id and self.project.company_id != self.company_id:
            raise ValidationError({"project": "Project must belong to the same company."})
        if self.supplier_id and self.company_id and self.supplier.company_id != self.company_id:
            raise ValidationError({"supplier": "Supplier must belong to the same company."})
        if self.source_timesheet_id and self.company_id and self.source_timesheet.company_id != self.company_id:
            raise ValidationError({"source_timesheet": "Timesheet must belong to the same company."})
        if self.source_timesheet_id and self.project_id and self.source_timesheet.project_id != self.project_id:
            raise ValidationError({"source_timesheet": "Timesheet project must match the settlement project."})


class SupplierSettlementLine(CompanyOwnedModel):
    settlement = models.ForeignKey(SupplierSettlement, on_delete=models.PROTECT, related_name="lines")
    worker = models.ForeignKey("rental_manpower.RentalWorker", on_delete=models.PROTECT, related_name="settlement_lines")
    worker_number = models.CharField(max_length=30)
    worker_name = models.CharField(max_length=200)
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)
    project_code = models.CharField(max_length=30)
    project_name = models.CharField(max_length=220)
    trade_summary = models.CharField(max_length=300)
    rate_summary = models.CharField(max_length=500)
    regular_hours = hours_field(default=Decimal("0"))
    work_days = models.PositiveIntegerField(default=0)
    overtime_hours = hours_field(default=Decimal("0"))
    base_amount = money_field(default=Decimal("0"))
    overtime_amount = money_field(default=Decimal("0"))
    gross_amount = money_field(default=Decimal("0"))
    adjustment_earnings = money_field(default=Decimal("0"))
    adjustment_deductions = money_field(default=Decimal("0"))
    net_amount = money_field(default=Decimal("0"))

    class Meta:
        db_table = "rental_supplier_settlement_line"
        ordering = ("worker_number", "worker_name")
        constraints = [
            models.UniqueConstraint(fields=("settlement", "worker"), name="rntl_set_line_worker_uniq"),
            models.CheckConstraint(condition=Q(regular_hours__gte=0), name="rntl_set_line_hrs_chk"),
            models.CheckConstraint(condition=Q(overtime_hours__gte=0), name="rntl_set_line_ot_hrs_chk"),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name="rntl_set_line_base_chk"),
            models.CheckConstraint(condition=Q(overtime_amount__gte=0), name="rntl_set_line_ot_amt_chk"),
            models.CheckConstraint(condition=Q(adjustment_earnings__gte=0), name="rntl_set_line_adj_er_chk"),
            models.CheckConstraint(condition=Q(adjustment_deductions__gte=0), name="rntl_set_line_adj_dd_chk"),
            models.CheckConstraint(condition=Q(gross_amount=models.F("base_amount") + models.F("overtime_amount")), name="rntl_set_line_gross_chk"),
            models.CheckConstraint(
                condition=Q(net_amount=models.F("gross_amount") + models.F("adjustment_earnings") - models.F("adjustment_deductions")),
                name="rntl_set_line_net_chk",
            ),
            models.CheckConstraint(condition=Q(net_amount__gte=0), name="rntl_set_line_net_pos_chk"),
        ]
        indexes = [models.Index(fields=("company", "settlement", "worker"), name="rntl_set_line_worker_idx")]


class SupplierSettlementRateLine(CompanyOwnedModel):
    settlement_line = models.ForeignKey(SupplierSettlementLine, on_delete=models.PROTECT, related_name="rate_lines")
    assignment = models.ForeignKey("rental_manpower.WorkerAssignment", on_delete=models.PROTECT, related_name="settlement_rate_lines")
    effective_from = models.DateField()
    effective_to = models.DateField()
    trade = models.CharField(max_length=120)
    rate_type = models.CharField(max_length=16, choices=RentalRateType.choices)
    rate = rate_field()
    regular_hours = hours_field(default=Decimal("0"))
    billable_days = models.PositiveIntegerField(default=0)
    calendar_days = models.PositiveIntegerField(default=0)
    base_amount = money_field(default=Decimal("0"))

    class Meta:
        db_table = "rental_supplier_settlement_rate"
        ordering = ("effective_from", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("settlement_line", "assignment"), name="rntl_set_rate_asg_uniq"),
            models.CheckConstraint(condition=Q(effective_to__gte=models.F("effective_from")), name="rntl_set_rate_dates_chk"),
            models.CheckConstraint(condition=Q(rate__gt=0), name="rntl_set_rate_pos_chk"),
            models.CheckConstraint(condition=Q(regular_hours__gte=0), name="rntl_set_rate_hrs_chk"),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name="rntl_set_rate_base_chk"),
        ]
        indexes = [models.Index(fields=("company", "settlement_line"), name="rntl_set_rate_line_idx")]


class SupplierSettlementAdjustmentLine(CompanyOwnedModel):
    settlement_line = models.ForeignKey(SupplierSettlementLine, on_delete=models.PROTECT, related_name="adjustment_lines")
    adjustment = models.ForeignKey(RentalAdjustment, on_delete=models.PROTECT, related_name="settlement_snapshot_lines")
    adjustment_type = models.CharField(max_length=24, choices=RentalAdjustmentType.choices)
    adjustment_label = models.CharField(max_length=100)
    effect = models.CharField(max_length=16, choices=RentalAdjustmentEffect.choices)
    amount = money_field()
    reason = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)
    transaction_date = models.DateField()

    class Meta:
        db_table = "rental_supplier_settlement_adjustment"
        ordering = ("transaction_date", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("settlement_line", "adjustment"), name="rntl_set_adj_line_uniq"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="rntl_set_adj_amt_pos_chk"),
            models.CheckConstraint(
                condition=Q(effect__in=[value for value, _label in RentalAdjustmentEffect.choices]),
                name="rntl_set_adj_effect_chk",
            ),
        ]
        indexes = [models.Index(fields=("company", "settlement_line"), name="rntl_set_adj_line_idx")]


class SupplierPaymentMethod(models.TextChoices):
    BANK = "bank", "Bank"
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"


class SupplierPaymentStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"
    CANCELLED = "cancelled", "Cancelled"


class SupplierPayment(CompanyOwnedModel):
    supplier = models.ForeignKey("rental_manpower.ManpowerSupplier", on_delete=models.PROTECT, related_name="payments")
    payment_number = models.CharField(max_length=40)
    payment_date = models.DateField()
    method = models.CharField(max_length=16, choices=SupplierPaymentMethod.choices)
    amount = money_field()
    status = models.CharField(max_length=16, choices=SupplierPaymentStatus.choices, default=SupplierPaymentStatus.PROCESSING, db_index=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=500, blank=True)
    result_reason = models.CharField(max_length=500, blank=True)
    supplier_code = models.CharField(max_length=30)
    supplier_name = models.CharField(max_length=200)
    paid_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    retry_of = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="retry_payments")

    class Meta:
        db_table = "rental_supplier_payment"
        ordering = ("-payment_date", "-created_at")
        constraints = [
            models.UniqueConstraint(fields=("company", "payment_number"), name="rntl_pay_no_uniq"),
            models.UniqueConstraint(fields=("company", "transaction_reference"), condition=~Q(transaction_reference=""), name="rntl_pay_ref_uniq"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="rntl_pay_amount_pos_chk"),
            models.CheckConstraint(condition=Q(method__in=[value for value, _label in SupplierPaymentMethod.choices]), name="rntl_pay_method_chk"),
            models.CheckConstraint(condition=Q(status__in=[value for value, _label in SupplierPaymentStatus.choices]), name="rntl_pay_status_chk"),
            models.CheckConstraint(
                condition=~Q(status=SupplierPaymentStatus.PAID) | Q(method=SupplierPaymentMethod.CASH) | ~Q(transaction_reference=""),
                name="rntl_pay_paid_ref_chk",
            ),
            models.CheckConstraint(
                condition=~Q(status__in=[SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED]) | ~Q(result_reason=""),
                name="rntl_pay_reason_chk",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "supplier", "-payment_date"), name="rntl_pay_supplier_idx"),
            models.Index(fields=("company", "status", "-payment_date"), name="rntl_pay_status_idx"),
        ]

    def clean(self) -> None:
        self.payment_number = (self.payment_number or "").strip().upper()
        self.transaction_reference = (self.transaction_reference or "").strip().upper()
        self.note = (self.note or "").strip()
        self.result_reason = (self.result_reason or "").strip()
        if self.amount is None or self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Payment amount must be greater than zero."})
        if self.company_id and self.supplier_id and self.supplier.company_id != self.company_id:
            raise ValidationError({"supplier": "Supplier must belong to the same company."})
        if self.status == SupplierPaymentStatus.PAID and self.method != SupplierPaymentMethod.CASH and not self.transaction_reference:
            raise ValidationError({"transaction_reference": "A bank/cheque reference is required before marking the payment Paid."})
        if self.status in {SupplierPaymentStatus.FAILED, SupplierPaymentStatus.REVERSED} and not self.result_reason:
            raise ValidationError({"result_reason": "A failure/reversal reason is required."})


class SupplierPaymentAllocation(CompanyOwnedModel):
    payment = models.ForeignKey(SupplierPayment, on_delete=models.PROTECT, related_name="allocations")
    settlement = models.ForeignKey(SupplierSettlement, on_delete=models.PROTECT, related_name="payment_allocations")
    amount = money_field()

    class Meta:
        db_table = "rental_supplier_payment_allocation"
        ordering = ("settlement__period_start", "created_at")
        constraints = [
            models.UniqueConstraint(fields=("payment", "settlement"), name="rntl_pay_alloc_uniq"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="rntl_pay_alloc_amt_chk"),
        ]
        indexes = [models.Index(fields=("company", "settlement"), name="rntl_pay_alloc_set_idx")]

    def clean(self) -> None:
        if self.company_id and self.payment_id and self.payment.company_id != self.company_id:
            raise ValidationError({"payment": "Payment must belong to the same company."})
        if self.company_id and self.settlement_id and self.settlement.company_id != self.company_id:
            raise ValidationError({"settlement": "Settlement must belong to the same company."})
        if self.payment_id and self.settlement_id and self.payment.supplier_id != self.settlement.supplier_id:
            raise ValidationError({"settlement": "Payment and settlement must belong to the same supplier."})
        if self.amount is None or self.amount <= Decimal("0"):
            raise ValidationError({"amount": "Allocation amount must be greater than zero."})
