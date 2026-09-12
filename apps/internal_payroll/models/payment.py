from __future__ import annotations

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.core.fields import EncryptedTextField, money_field
from apps.core.encryption import sensitive_fingerprint
from apps.core.models import CompanyOwnedModel


IBAN_RE = re.compile(r"^[A-Z]{2}[0-9A-Z]{13,32}$")


def normalize_iban(value: str) -> str:
    return re.sub(r"\s+", "", (value or "").upper())


def iban_is_valid(value: str) -> bool:
    iban = normalize_iban(value)
    if not IBAN_RE.fullmatch(iban):
        return False
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(ord(ch) - 55) if ch.isalpha() else ch for ch in rearranged)
    remainder = 0
    for offset in range(0, len(numeric), 9):
        remainder = int(str(remainder) + numeric[offset : offset + 9]) % 97
    return remainder == 1


class PaymentDestination(models.TextChoices):
    IBAN = "iban", "Bank account / IBAN"
    SALARY_CARD = "salary_card", "Salary card"


class EmployeePaymentProfile(CompanyOwnedModel):
    """Current employee salary-payment destination.

    Historical payment batches snapshot these fields and never depend on later edits.
    """

    employee = models.OneToOneField(
        "internal_payroll.InternalEmployee",
        on_delete=models.PROTECT,
        related_name="payment_profile",
    )
    destination_type = models.CharField(max_length=20, choices=PaymentDestination.choices, default=PaymentDestination.IBAN)
    account_holder_name = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=160)
    bank_code = models.CharField(max_length=40, blank=True)
    iban = EncryptedTextField(blank=True)
    iban_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    salary_card_number = EncryptedTextField(blank=True)
    salary_card_fingerprint = models.CharField(max_length=64, blank=True, db_index=True)
    wps_enabled = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="verified_salary_payment_profiles",
    )

    class Meta:
        db_table = "internal_employee_payment_profile"
        constraints = [
            models.UniqueConstraint(
                fields=("company", "iban_fingerprint"),
                condition=~Q(iban_fingerprint=""),
                name="int_pay_profile_company_iban_uniq",
            ),
            models.UniqueConstraint(
                fields=("company", "salary_card_fingerprint"),
                condition=~Q(salary_card_fingerprint=""),
                name="int_pay_profile_company_card_uniq",
            ),
            models.CheckConstraint(
                condition=Q(destination_type__in=[value for value, _label in PaymentDestination.choices]),
                name="int_pay_profile_destination_valid",
            ),
            models.CheckConstraint(
                condition=(Q(destination_type=PaymentDestination.IBAN) & ~Q(iban_fingerprint="") & Q(salary_card_fingerprint=""))
                | (Q(destination_type=PaymentDestination.SALARY_CARD) & Q(iban_fingerprint="") & ~Q(salary_card_fingerprint="")),
                name="int_pay_profile_destination_fields",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "is_active", "bank_name"), name="int_pay_profile_active_idx"),
        ]

    def clean(self) -> None:
        self.account_holder_name = self.account_holder_name.strip()
        self.bank_name = self.bank_name.strip()
        self.bank_code = self.bank_code.strip().upper()
        self.iban = normalize_iban(self.iban)
        self.salary_card_number = self.salary_card_number.strip().upper()
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if not self.account_holder_name:
            raise ValidationError({"account_holder_name": "Account holder name is required."})
        if not self.bank_name:
            raise ValidationError({"bank_name": "Bank or salary-card issuer is required."})
        if self.destination_type == PaymentDestination.IBAN:
            self.salary_card_number = ""
            if not self.iban:
                raise ValidationError({"iban": "IBAN is required for a bank-account payment profile."})
            if not iban_is_valid(self.iban):
                raise ValidationError({"iban": "Enter a valid IBAN."})
            if self.company_id:
                country = getattr(getattr(self.company, "settings", None), "country_code", "")
                if country == "SA" and not self.iban.startswith("SA"):
                    raise ValidationError({"iban": "Saudi company salary accounts must use a Saudi IBAN."})
        elif self.destination_type == PaymentDestination.SALARY_CARD:
            self.iban = ""
            if not self.salary_card_number:
                raise ValidationError({"salary_card_number": "Salary card number is required."})
        self.iban_fingerprint = sensitive_fingerprint(self.iban)
        self.salary_card_fingerprint = sensitive_fingerprint(self.salary_card_number)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.employee} · {self.get_destination_type_display()}"


class CompanySalaryPaymentSettings(CompanyOwnedModel):
    """Company-level bank/WPS identity. Blank fields are reported as readiness blockers, not invented defaults."""

    employer_identifier = models.CharField(max_length=100, blank=True)
    employer_bank_name = models.CharField(max_length=160, blank=True)
    employer_bank_code = models.CharField(max_length=40, blank=True)
    employer_iban = EncryptedTextField(blank=True)
    bank_customer_reference = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = "internal_salary_payment_settings"
        constraints = [models.UniqueConstraint(fields=("company",), name="int_pay_settings_company_uniq")]

    def clean(self) -> None:
        self.employer_identifier = self.employer_identifier.strip().upper()
        self.employer_bank_name = self.employer_bank_name.strip()
        self.employer_bank_code = self.employer_bank_code.strip().upper()
        self.employer_iban = normalize_iban(self.employer_iban)
        self.bank_customer_reference = self.bank_customer_reference.strip().upper()
        if self.employer_iban and not iban_is_valid(self.employer_iban):
            raise ValidationError({"employer_iban": "Enter a valid employer IBAN."})
        if self.company_id:
            country = getattr(getattr(self.company, "settings", None), "country_code", "")
            if country == "SA" and self.employer_iban and not self.employer_iban.startswith("SA"):
                raise ValidationError({"employer_iban": "Saudi company payment settings must use a Saudi IBAN."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Salary payment settings · {self.company}"


class BankExportChannel(models.TextChoices):
    BANK_CSV = "bank_csv", "Bank CSV"
    WPS = "wps", "WPS wage data"


class BankExportDelimiter(models.TextChoices):
    COMMA = "comma", "Comma"
    TAB = "tab", "Tab"
    SEMICOLON = "semicolon", "Semicolon"


class BankExportEncoding(models.TextChoices):
    UTF8 = "utf-8", "UTF-8"
    UTF8_BOM = "utf-8-sig", "UTF-8 with BOM"


EXPORT_FIELD_LABELS: dict[str, str] = {
    "employee_number": "Employee ID",
    "employee_name": "Employee name",
    "national_id": "National ID / Iqama",
    "employee_address": "Employee address",
    "bank_name": "Bank name",
    "bank_code": "Bank code",
    "iban": "IBAN",
    "salary_card_number": "Salary card number",
    "account_holder_name": "Account holder",
    "basic_salary": "Basic salary",
    "housing_allowance": "Housing allowance",
    "other_earnings": "Other earnings",
    "deductions": "Deductions",
    "net_salary": "Net salary",
    "transaction_reference": "Transaction reference",
    "period_start": "Period start",
    "period_end": "Period end",
    "employer_identifier": "Employer identifier",
    "employer_bank_name": "Employer bank name",
    "employer_bank_code": "Employer bank code",
    "employer_iban": "Employer IBAN",
    "bank_customer_reference": "Bank customer reference",
}


class BankExportTemplate(CompanyOwnedModel):
    code = models.CharField(max_length=40)
    name = models.CharField(max_length=160)
    channel = models.CharField(max_length=20, choices=BankExportChannel.choices, default=BankExportChannel.BANK_CSV)
    delimiter = models.CharField(max_length=16, choices=BankExportDelimiter.choices, default=BankExportDelimiter.COMMA)
    encoding = models.CharField(max_length=16, choices=BankExportEncoding.choices, default=BankExportEncoding.UTF8)
    include_header = models.BooleanField(default=True)
    columns = models.JSONField(default=list)
    headers = models.JSONField(default=list)
    result_columns = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        db_table = "internal_bank_export_template"
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(fields=("company", "code"), name="int_bank_template_company_code_uniq"),
            models.UniqueConstraint(fields=("company", "name"), name="int_bank_template_company_name_uniq"),
            models.CheckConstraint(
                condition=Q(channel__in=[value for value, _label in BankExportChannel.choices]),
                name="int_bank_template_channel_valid",
            ),
            models.CheckConstraint(
                condition=Q(delimiter__in=[value for value, _label in BankExportDelimiter.choices]),
                name="int_bank_template_delim_valid",
            ),
            models.CheckConstraint(
                condition=Q(encoding__in=[value for value, _label in BankExportEncoding.choices]),
                name="int_bank_template_encoding_valid",
            ),
        ]
        indexes = [models.Index(fields=("company", "channel", "is_active"), name="int_bank_template_active_idx")]

    def clean(self) -> None:
        self.code = self.code.strip().upper()
        self.name = self.name.strip()
        if not self.code:
            raise ValidationError({"code": "Template code is required."})
        if not self.name:
            raise ValidationError({"name": "Template name is required."})
        if not isinstance(self.columns, list) or not self.columns:
            raise ValidationError({"columns": "At least one export column is required."})
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in self.columns:
            key = str(raw).strip()
            if key not in EXPORT_FIELD_LABELS:
                raise ValidationError({"columns": f"Unsupported export field: {key or 'blank'}."})
            if key in seen:
                raise ValidationError({"columns": f"Export field {key} is duplicated."})
            seen.add(key)
            normalized.append(key)
        # Bank/WPS layouts are bank-owned contracts. Some valid Saudi payroll files
        # identify rows by IBAN + national ID and deliberately omit our internal
        # employee number, so only the payable amount is universally mandatory.
        if "net_salary" not in seen:
            raise ValidationError({"columns": "Net salary is required in every payment export."})
        self.columns = normalized
        if not self.headers:
            self.headers = [EXPORT_FIELD_LABELS[key] for key in normalized]
        if not isinstance(self.headers, list) or len(self.headers) != len(normalized):
            raise ValidationError({"headers": "Export headers must contain exactly one label for each export column."})
        cleaned_headers = [str(item).strip() for item in self.headers]
        if any(not item for item in cleaned_headers):
            raise ValidationError({"headers": "Export header labels cannot be blank."})
        if len({item.casefold() for item in cleaned_headers}) != len(cleaned_headers):
            raise ValidationError({"headers": "Export header labels must be unique."})
        self.headers = cleaned_headers
        if not isinstance(self.result_columns, dict):
            raise ValidationError({"result_columns": "Result column mapping must be an object."})
        allowed_result_keys = {"employee", "status", "reference", "reason"}
        unexpected = set(self.result_columns) - allowed_result_keys
        if unexpected:
            raise ValidationError({"result_columns": f"Unsupported result mapping key: {sorted(unexpected)[0]}."})
        cleaned_result = {str(key): str(value).strip() for key, value in self.result_columns.items() if str(value).strip()}
        if cleaned_result and (not cleaned_result.get("employee") or not cleaned_result.get("status")):
            raise ValidationError({"result_columns": "Configured result mapping requires both Employee ID and Status headers."})
        self.result_columns = cleaned_result

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.code} · {self.name}"


class SalaryPaymentBatchStatus(models.TextChoices):
    PREPARED = "prepared", "Prepared"
    EXPORTED = "exported", "Exported"
    PROCESSING = "processing", "Processing"
    PARTIALLY_PAID = "partially_paid", "Partially Paid"
    ATTENTION = "attention", "Needs Attention"
    PAID = "paid", "Paid"
    CLOSED = "closed", "Closed"
    CANCELLED = "cancelled", "Cancelled"


class SalaryPaymentBatch(CompanyOwnedModel):
    run = models.ForeignKey("internal_payroll.PayrollRun", on_delete=models.PROTECT, related_name="payment_batches")
    reference = models.CharField(max_length=60)
    channel = models.CharField(max_length=20, choices=BankExportChannel.choices)
    export_template = models.ForeignKey(
        BankExportTemplate,
        on_delete=models.PROTECT,
        related_name="payment_batches",
        null=True,
        blank=True,
    )
    template_code = models.CharField(max_length=40)
    template_name = models.CharField(max_length=160)
    delimiter = models.CharField(max_length=16, choices=BankExportDelimiter.choices)
    encoding = models.CharField(max_length=16, choices=BankExportEncoding.choices)
    include_header = models.BooleanField(default=True)
    columns = models.JSONField(default=list)
    headers = models.JSONField(default=list)
    result_columns = models.JSONField(default=dict)
    status = models.CharField(max_length=24, choices=SalaryPaymentBatchStatus.choices, default=SalaryPaymentBatchStatus.PREPARED, db_index=True)
    employee_count = models.PositiveIntegerField(default=0)
    total_amount = money_field(default=Decimal("0"))
    paid_amount = money_field(default=Decimal("0"))
    source_fingerprint = models.CharField(max_length=64)
    last_export_sha256 = models.CharField(max_length=64, blank=True)
    employer_identifier = models.CharField(max_length=100, blank=True)
    employer_bank_name = models.CharField(max_length=160, blank=True)
    employer_bank_code = models.CharField(max_length=40, blank=True)
    employer_iban = EncryptedTextField(blank=True)
    bank_customer_reference = models.CharField(max_length=100, blank=True)
    prepared_at = models.DateTimeField()
    prepared_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="prepared_salary_payment_batches")
    exported_at = models.DateTimeField(null=True, blank=True)
    exported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="exported_salary_payment_batches")
    processing_at = models.DateTimeField(null=True, blank=True)
    processing_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="processing_salary_payment_batches")
    completed_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_salary_payment_batches")
    note = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "internal_salary_payment_batch"
        ordering = ("-prepared_at",)
        constraints = [
            models.UniqueConstraint(fields=("company", "reference"), name="int_pay_batch_company_ref_uniq"),
            models.CheckConstraint(condition=Q(employee_count__gte=0), name="int_pay_batch_employee_count_nonneg"),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name="int_pay_batch_total_nonneg"),
            models.CheckConstraint(condition=Q(paid_amount__gte=0), name="int_pay_batch_paid_nonneg"),
            models.CheckConstraint(condition=Q(paid_amount__lte=models.F("total_amount")), name="int_pay_batch_paid_lte_total"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SalaryPaymentBatchStatus.choices]),
                name="int_pay_batch_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=[value for value, _label in BankExportChannel.choices]),
                name="int_pay_batch_channel_valid",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "run", "status"), name="int_pay_batch_run_status_idx"),
            models.Index(fields=("company", "channel", "-prepared_at"), name="int_pay_batch_channel_idx"),
        ]

    def clean(self) -> None:
        self.reference = self.reference.strip().upper()
        self.note = self.note.strip()
        self.employer_identifier = self.employer_identifier.strip().upper()
        self.employer_bank_name = self.employer_bank_name.strip()
        self.employer_bank_code = self.employer_bank_code.strip().upper()
        self.employer_iban = normalize_iban(self.employer_iban)
        self.bank_customer_reference = self.bank_customer_reference.strip().upper()
        if self.company_id and self.run_id and self.run.company_id != self.company_id:
            raise ValidationError({"run": "Payroll run must belong to the same company."})
        if self.company_id and self.export_template_id and self.export_template.company_id != self.company_id:
            raise ValidationError({"export_template": "Export template must belong to the same company."})
        if self.export_template_id and self.export_template.channel != self.channel:
            raise ValidationError({"export_template": "Export template channel does not match the payment batch."})
        self.template_code = self.template_code.strip().upper()
        self.template_name = self.template_name.strip()
        if not self.template_code or not self.template_name:
            raise ValidationError({"export_template": "Payment batch must snapshot an export template."})
        if not isinstance(self.columns, list) or not self.columns:
            raise ValidationError({"columns": "Payment batch export columns are missing."})
        if any(str(item) not in EXPORT_FIELD_LABELS for item in self.columns):
            raise ValidationError({"columns": "Payment batch contains an unsupported export field."})
        if not isinstance(self.headers, list) or len(self.headers) != len(self.columns) or any(not str(item).strip() for item in self.headers):
            raise ValidationError({"headers": "Payment batch export headers do not match its export columns."})
        self.headers = [str(item).strip() for item in self.headers]
        if len({item.casefold() for item in self.headers}) != len(self.headers):
            raise ValidationError({"headers": "Payment batch export header labels must be unique."})
        if not isinstance(self.result_columns, dict):
            raise ValidationError({"result_columns": "Payment result mapping snapshot is invalid."})
        allowed_result_keys = {"employee", "status", "reference", "reason"}
        unexpected = set(self.result_columns) - allowed_result_keys
        if unexpected:
            raise ValidationError({"result_columns": "Payment result mapping snapshot contains unsupported keys."})
        if self.result_columns and (not str(self.result_columns.get("employee") or "").strip() or not str(self.result_columns.get("status") or "").strip()):
            raise ValidationError({"result_columns": "Payment result mapping snapshot requires Employee ID and Status headers."})
        self.result_columns = {str(key): str(value).strip() for key, value in self.result_columns.items() if str(value).strip()}
        if not self.reference:
            raise ValidationError({"reference": "Payment batch reference is required."})

    def __str__(self) -> str:
        return f"{self.reference} · {self.get_status_display()}"


class SalaryPaymentRowStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"
    CANCELLED = "cancelled", "Cancelled"


class SalaryPaymentRow(CompanyOwnedModel):
    batch = models.ForeignKey(SalaryPaymentBatch, on_delete=models.PROTECT, related_name="rows")
    run_line = models.ForeignKey("internal_payroll.PayrollRunLine", on_delete=models.PROTECT, related_name="payment_rows")
    employee = models.ForeignKey("internal_payroll.InternalEmployee", on_delete=models.PROTECT, related_name="salary_payment_rows")
    claim_active = models.BooleanField(default=True, db_index=True)
    employee_number = models.CharField(max_length=40)
    employee_name = models.CharField(max_length=200)
    national_id = models.CharField(max_length=50)
    employee_address = models.CharField(max_length=300, blank=True)
    destination_type = models.CharField(max_length=20, choices=PaymentDestination.choices)
    account_holder_name = models.CharField(max_length=200)
    bank_name = models.CharField(max_length=160)
    bank_code = models.CharField(max_length=40, blank=True)
    iban = EncryptedTextField(blank=True)
    salary_card_number = EncryptedTextField(blank=True)
    destination_fingerprint = models.CharField(max_length=64, blank=True)
    amount = money_field()
    basic_salary = money_field(default=Decimal("0"))
    housing_allowance = money_field(default=Decimal("0"))
    other_earnings = money_field(default=Decimal("0"))
    deductions = money_field(default=Decimal("0"))
    status = models.CharField(max_length=20, choices=SalaryPaymentRowStatus.choices, default=SalaryPaymentRowStatus.PENDING, db_index=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    failure_reason = models.CharField(max_length=500, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    paid_at = models.DateTimeField(null=True, blank=True)
    last_result_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "internal_salary_payment_row"
        ordering = ("employee_number",)
        constraints = [
            models.UniqueConstraint(fields=("batch", "run_line"), name="int_pay_row_batch_line_uniq"),
            models.UniqueConstraint(
                fields=("run_line",),
                condition=Q(claim_active=True),
                name="int_pay_row_active_line_uniq",
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name="int_pay_row_amount_positive"),
            models.CheckConstraint(condition=Q(basic_salary__gte=0), name="int_pay_row_basic_nonneg"),
            models.CheckConstraint(condition=Q(housing_allowance__gte=0), name="int_pay_row_housing_nonneg"),
            models.CheckConstraint(condition=Q(other_earnings__gte=0), name="int_pay_row_other_earn_nonneg"),
            models.CheckConstraint(condition=Q(deductions__gte=0), name="int_pay_row_deductions_nonneg"),
            models.CheckConstraint(condition=Q(attempt_count__gte=0), name="int_pay_row_attempt_nonneg"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SalaryPaymentRowStatus.choices]),
                name="int_pay_row_status_valid",
            ),
            models.CheckConstraint(
                condition=(Q(destination_type=PaymentDestination.IBAN) & ~Q(destination_fingerprint=""))
                | (Q(destination_type=PaymentDestination.SALARY_CARD) & ~Q(destination_fingerprint="")),
                name="int_pay_row_destination_fields",
            ),
        ]
        indexes = [
            models.Index(fields=("company", "batch", "status"), name="int_pay_row_batch_status_idx"),
            models.Index(fields=("company", "employee", "-created_at"), name="int_pay_row_employee_idx"),
        ]

    def clean(self) -> None:
        self.employee_number = self.employee_number.strip().upper()
        self.employee_name = self.employee_name.strip()
        self.national_id = self.national_id.strip().upper()
        self.employee_address = self.employee_address.strip()
        self.account_holder_name = self.account_holder_name.strip()
        self.bank_name = self.bank_name.strip()
        self.bank_code = self.bank_code.strip().upper()
        self.iban = normalize_iban(self.iban)
        self.salary_card_number = self.salary_card_number.strip().upper()
        if self.destination_type == PaymentDestination.IBAN:
            self.salary_card_number = ""
            if not self.iban or not iban_is_valid(self.iban):
                raise ValidationError({"iban": "Payment snapshot requires a valid IBAN."})
        elif self.destination_type == PaymentDestination.SALARY_CARD:
            self.iban = ""
            if not self.salary_card_number:
                raise ValidationError({"salary_card_number": "Payment snapshot requires a salary card number."})
        self.transaction_reference = self.transaction_reference.strip().upper()
        self.failure_reason = self.failure_reason.strip()
        if self.company_id and self.batch_id and self.batch.company_id != self.company_id:
            raise ValidationError({"batch": "Payment batch must belong to the same company."})
        if self.company_id and self.run_line_id and self.run_line.company_id != self.company_id:
            raise ValidationError({"run_line": "Payroll line must belong to the same company."})
        if self.company_id and self.employee_id and self.employee.company_id != self.company_id:
            raise ValidationError({"employee": "Employee must belong to the same company."})
        if self.batch_id and self.run_line_id and self.run_line.run_id != self.batch.run_id:
            raise ValidationError({"run_line": "Payment row must use a payroll line from its batch payroll run."})
        if self.run_line_id and self.employee_id and self.run_line.employee_id != self.employee_id:
            raise ValidationError({"employee": "Payment employee does not match the payroll line."})
        self.destination_fingerprint = sensitive_fingerprint(self.iban if self.destination_type == PaymentDestination.IBAN else self.salary_card_number)
        if self.amount <= 0:
            raise ValidationError({"amount": "Salary payment amount must be greater than zero."})
        if self.amount != self.run_line.net:
            raise ValidationError({"amount": "Salary payment amount must equal the approved payroll net amount."})

    def __str__(self) -> str:
        return f"{self.batch.reference} · {self.employee_number} · {self.amount}"


class SalaryPaymentAttemptStatus(models.TextChoices):
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"


class SalaryPaymentAttempt(CompanyOwnedModel):
    row = models.ForeignKey(SalaryPaymentRow, on_delete=models.PROTECT, related_name="attempts")
    attempt_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=SalaryPaymentAttemptStatus.choices, default=SalaryPaymentAttemptStatus.PROCESSING)
    started_at = models.DateTimeField()
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="started_salary_payment_attempts")
    finished_at = models.DateTimeField(null=True, blank=True)
    transaction_reference = models.CharField(max_length=120, blank=True)
    failure_reason = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = "internal_salary_payment_attempt"
        ordering = ("attempt_number",)
        constraints = [
            models.UniqueConstraint(fields=("row", "attempt_number"), name="int_pay_attempt_row_number_uniq"),
            models.CheckConstraint(condition=Q(attempt_number__gt=0), name="int_pay_attempt_number_positive"),
            models.CheckConstraint(
                condition=Q(status__in=[value for value, _label in SalaryPaymentAttemptStatus.choices]),
                name="int_pay_attempt_status_valid",
            ),
        ]
        indexes = [models.Index(fields=("company", "row", "attempt_number"), name="int_pay_attempt_row_idx")]

    def clean(self) -> None:
        self.transaction_reference = self.transaction_reference.strip().upper()
        self.failure_reason = self.failure_reason.strip()
        if self.company_id and self.row_id and self.row.company_id != self.company_id:
            raise ValidationError({"row": "Payment attempt must belong to the same company."})


class SalaryPaymentResultImport(CompanyOwnedModel):
    batch = models.ForeignKey(SalaryPaymentBatch, on_delete=models.PROTECT, related_name="result_imports")
    file_name = models.CharField(max_length=255)
    content_sha256 = models.CharField(max_length=64)
    updated_rows = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    imported_at = models.DateTimeField()
    imported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="salary_payment_result_imports")

    class Meta:
        db_table = "internal_salary_payment_result_import"
        ordering = ("-imported_at",)
        constraints = [
            models.UniqueConstraint(fields=("batch", "content_sha256"), name="int_pay_result_batch_hash_uniq"),
        ]
        indexes = [models.Index(fields=("company", "batch", "-imported_at"), name="int_pay_result_batch_idx")]

    def clean(self) -> None:
        self.file_name = self.file_name.strip()[:255]
        if self.company_id and self.batch_id and self.batch.company_id != self.company_id:
            raise ValidationError({"batch": "Result import must belong to the same company."})
