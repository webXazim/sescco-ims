from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_edit, membership_can_workspace, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.core.services.numbering import allocate_number
from apps.internal_payroll.models import (
    BankExportChannel,
    BankExportDelimiter,
    BankExportTemplate,
    CompanySalaryPaymentSettings,
    EmployeePaymentProfile,
    InternalEmployee,
    PayrollRun,
    PayrollRunLine,
    PayrollRunLineAdjustment,
    PayrollRunLineComponent,
    PayrollRunStatus,
    PaymentDestination,
    SalaryPaymentAttempt,
    SalaryPaymentAttemptStatus,
    SalaryPaymentBatch,
    SalaryPaymentBatchStatus,
    SalaryPaymentResultImport,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
    WPSMapping,
)
from apps.internal_payroll.services.payroll import verify_payroll_run_integrity


def _money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def _require_internal_edit(membership: CompanyMembership) -> None:
    if not membership_can_edit(membership, Workspace.INTERNAL):
        raise PermissionDenied("Your role cannot edit Internal Company payroll data.")


def _require_pay(membership: CompanyMembership) -> None:
    if not membership_can_workspace(membership, Workspace.INTERNAL) or not membership_has_capability(membership, Capability.PAY):
        raise PermissionDenied("Your role cannot execute or reconcile salary payments.")


def _masked(value: str, *, visible: int = 4) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= visible:
        return "•" * len(text)
    return f"{'•' * min(12, len(text) - visible)}{text[-visible:]}"


def _profile_audit(profile: EmployeePaymentProfile) -> dict[str, object]:
    destination = profile.iban if profile.destination_type == PaymentDestination.IBAN else profile.salary_card_number
    return {
        "employee_id": str(profile.employee_id),
        "destination_type": profile.destination_type,
        "bank_name": profile.bank_name,
        "bank_code": profile.bank_code,
        "destination_masked": _masked(destination),
        "wps_enabled": profile.wps_enabled,
        "is_active": profile.is_active,
        "verified_at": profile.verified_at.isoformat() if profile.verified_at else None,
    }


@transaction.atomic
def upsert_employee_payment_profile(
    *,
    actor_membership: CompanyMembership,
    employee_id,
    values: dict[str, object],
    request: HttpRequest | None = None,
) -> EmployeePaymentProfile:
    """Create or patch the current salary-payment destination.

    Omitted fields are preserved on an existing profile. Sensitive destination
    values are never accepted as masked placeholders.
    """
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    employee = InternalEmployee.objects.select_for_update().for_company(company).get(pk=employee_id)
    profile = EmployeePaymentProfile.objects.select_for_update().for_company(company).filter(employee=employee).first()
    before = _profile_audit(profile) if profile else {}
    creating = profile is None
    if profile is None:
        profile = EmployeePaymentProfile(company=company, employee=employee)

    text_fields = (
        "destination_type", "account_holder_name", "bank_name", "bank_code",
        "iban", "salary_card_number",
    )
    for field in text_fields:
        if field not in values:
            continue
        value = str(values[field] or "")
        if field in {"iban", "salary_card_number"} and "•" in value:
            raise ValidationError({field: "Masked payment values cannot be saved. Enter the complete value when changing it."})
        setattr(profile, field, value)
    if "wps_enabled" in values:
        profile.wps_enabled = bool(values["wps_enabled"])
    if "is_active" in values:
        profile.is_active = bool(values["is_active"])
    if values.get("mark_verified") is True:
        profile.verified_at = timezone.now()
        profile.verified_by = actor_membership.user

    if creating:
        required = {"destination_type", "account_holder_name", "bank_name"}
        missing = sorted(field for field in required if not str(getattr(profile, field, "") or "").strip())
        if missing:
            raise ValidationError({field: "This field is required when creating a payment profile." for field in missing})
    profile.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.employee_payment_profile.created" if creating else "internal.employee_payment_profile.updated",
        object_type="internal_payroll.EmployeePaymentProfile",
        object_id=profile.pk,
        object_label=f"{employee.employee_number} · salary payment profile",
        actor_membership=actor_membership,
        before=before,
        after=_profile_audit(profile),
        request=request,
    )
    return profile


@transaction.atomic
def update_company_salary_payment_settings(
    *, actor_membership: CompanyMembership, values: dict[str, object], request: HttpRequest | None = None
) -> CompanySalaryPaymentSettings:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    settings_row = CompanySalaryPaymentSettings.objects.select_for_update().for_company(company).first()
    if settings_row is None:
        settings_row = CompanySalaryPaymentSettings(company=company)
    before = {
        "employer_identifier": settings_row.employer_identifier,
        "employer_bank_name": settings_row.employer_bank_name,
        "employer_bank_code": settings_row.employer_bank_code,
        "employer_iban_masked": _masked(settings_row.employer_iban),
        "bank_customer_reference": settings_row.bank_customer_reference,
    }
    for field in ("employer_identifier", "employer_bank_name", "employer_bank_code", "employer_iban", "bank_customer_reference"):
        if field in values:
            setattr(settings_row, field, str(values[field] or ""))
    settings_row.save()
    after = {
        "employer_identifier": settings_row.employer_identifier,
        "employer_bank_name": settings_row.employer_bank_name,
        "employer_bank_code": settings_row.employer_bank_code,
        "employer_iban_masked": _masked(settings_row.employer_iban),
        "bank_customer_reference": settings_row.bank_customer_reference,
    }
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_settings.updated",
        object_type="internal_payroll.CompanySalaryPaymentSettings",
        object_id=settings_row.pk,
        object_label="Salary payment settings",
        actor_membership=actor_membership,
        before=before,
        after=after,
        request=request,
    )
    return settings_row


@transaction.atomic
def create_bank_export_template(
    *,
    actor_membership: CompanyMembership,
    code: str,
    name: str,
    channel: str,
    delimiter: str,
    encoding: str,
    include_header: bool,
    columns: list[str],
    headers: list[str] | None = None,
    result_columns: dict[str, str] | None = None,
    is_active: bool = True,
    request: HttpRequest | None = None,
) -> BankExportTemplate:
    _require_internal_edit(actor_membership)
    template = BankExportTemplate(
        company=actor_membership.company,
        code=code,
        name=name,
        channel=channel,
        delimiter=delimiter,
        encoding=encoding,
        include_header=bool(include_header),
        columns=columns,
        headers=headers or [],
        result_columns=result_columns or {},
        is_active=bool(is_active),
    )
    template.save()
    record_audit_event(
        company=template.company,
        area=AuditArea.INTERNAL,
        action="internal.bank_export_template.created",
        object_type="internal_payroll.BankExportTemplate",
        object_id=template.pk,
        object_label=str(template),
        actor_membership=actor_membership,
        after={"code": template.code, "name": template.name, "channel": template.channel, "columns": template.columns, "headers": template.headers, "result_columns": template.result_columns, "active": template.is_active},
        request=request,
    )
    return template


@transaction.atomic
def update_bank_export_template(
    *, actor_membership: CompanyMembership, template_id, values: dict[str, object], request: HttpRequest | None = None
) -> BankExportTemplate:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    template = BankExportTemplate.objects.select_for_update().for_company(company).get(pk=template_id)
    before = {"code": template.code, "name": template.name, "channel": template.channel, "delimiter": template.delimiter, "encoding": template.encoding, "include_header": template.include_header, "columns": list(template.columns), "headers": list(template.headers), "result_columns": dict(template.result_columns), "active": template.is_active}
    for field in ("code", "name", "channel", "delimiter", "encoding", "include_header", "columns", "headers", "result_columns", "is_active"):
        if field in values:
            setattr(template, field, values[field])
    template.save()
    after = {"code": template.code, "name": template.name, "channel": template.channel, "delimiter": template.delimiter, "encoding": template.encoding, "include_header": template.include_header, "columns": list(template.columns), "headers": list(template.headers), "result_columns": dict(template.result_columns), "active": template.is_active}
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.bank_export_template.updated",
        object_type="internal_payroll.BankExportTemplate",
        object_id=template.pk,
        object_label=str(template),
        actor_membership=actor_membership,
        before=before,
        after=after,
        request=request,
    )
    return template


def _wps_breakdown(line: PayrollRunLine) -> tuple[dict[str, Decimal], list[str]]:
    components = list(
        PayrollRunLineComponent.objects.for_company(line.company)
        .filter(run_line=line)
        .order_by("component_code", "effective_from")
    )
    adjustments = list(
        PayrollRunLineAdjustment.objects.for_company(line.company)
        .filter(run_line=line)
        .order_by("transaction_date", "id")
    )
    basic = Decimal("0")
    housing = Decimal("0")
    other = Decimal("0")
    deductions = Decimal("0")
    blockers: list[str] = []
    for component in components:
        if component.wps_mapping == WPSMapping.BASIC_SALARY:
            basic += component.amount
        elif component.wps_mapping == WPSMapping.HOUSING_ALLOWANCE:
            housing += component.amount
        elif component.wps_mapping == WPSMapping.OTHER_EARNINGS:
            other += component.amount
        elif component.wps_mapping == WPSMapping.DEDUCTIONS:
            deductions += component.amount
        elif component.amount > 0:
            blockers.append(f"Salary component {component.component_code} is not mapped for WPS.")
    other += line.overtime_amount
    for adjustment in adjustments:
        if adjustment.effect == "earning":
            other += adjustment.amount
        else:
            deductions += adjustment.amount
    result = {
        "basic_salary": _money(basic),
        "housing_allowance": _money(housing),
        "other_earnings": _money(other),
        "deductions": _money(deductions),
    }
    expected = _money(result["basic_salary"] + result["housing_allowance"] + result["other_earnings"] - result["deductions"])
    if expected != line.net:
        blockers.append("WPS component mapping does not reconcile to the approved payroll net amount.")
    if result["basic_salary"] <= 0:
        blockers.append("WPS Basic Salary mapping is missing from the approved payroll snapshot.")
    return result, blockers


def payment_readiness(*, company, run: PayrollRun, channel: str, template: BankExportTemplate | None = None) -> dict[str, object]:
    if channel not in BankExportChannel.values:
        raise ValidationError({"channel": "Unsupported salary payment channel."})
    if template is not None:
        if template.company_id != company.pk or not template.is_active:
            raise ValidationError({"template": "Choose an active company export template."})
        if template.channel != channel:
            raise ValidationError({"template": "Export template channel does not match the payment channel."})
    company_settings = CompanySalaryPaymentSettings.objects.for_company(company).first()
    company_blockers: list[str] = []
    if template is None:
        company_blockers.append(f"An active {'WPS' if channel == BankExportChannel.WPS else 'bank'} export template is required.")
    required_company_fields = set(template.columns) if template else set()
    if channel == BankExportChannel.WPS:
        required_company_fields.update({"employer_identifier", "employer_bank_name", "employer_iban"})
    company_requirements = {
        "employer_identifier": ("employer_identifier", "Employer identifier is not configured."),
        "employer_bank_name": ("employer_bank_name", "Employer bank name is not configured."),
        "employer_bank_code": ("employer_bank_code", "Employer bank code is not configured."),
        "employer_iban": ("employer_iban", "Employer IBAN is not configured."),
        "bank_customer_reference": ("bank_customer_reference", "Bank customer reference is not configured."),
    }
    for export_key, (field_name, message) in company_requirements.items():
        if export_key in required_company_fields and (not company_settings or not getattr(company_settings, field_name)):
            company_blockers.append(message)

    lines = list(
        PayrollRunLine.objects.for_company(company)
        .filter(run=run)
        .select_related("employee")
        .order_by("employee_number")
    )
    profiles = {str(row.employee_id): row for row in EmployeePaymentProfile.objects.for_company(company).filter(employee_id__in=[line.employee_id for line in lines])}
    active_claims = set(
        SalaryPaymentRow.objects.for_company(company)
        .filter(run_line_id__in=[line.pk for line in lines], claim_active=True)
        .values_list("run_line_id", flat=True)
    )
    rows: list[dict[str, object]] = []
    ready_count = 0
    for line in lines:
        # A zero-net approved payroll line is financially complete without a bank transfer.
        # It must not block payable employees or create a meaningless payment row.
        if line.net == 0:
            continue
        if line.net < 0:
            raise ValidationError({"payroll": f"Employee {line.employee_number} has an invalid negative approved net salary."})
        blockers: list[str] = []
        profile = profiles.get(str(line.employee_id))
        if line.pk in active_claims:
            blockers.append("This payroll line already belongs to an active salary payment lifecycle.")
        if profile is None or not profile.is_active:
            blockers.append("Active salary payment profile is missing.")
        breakdown = {
            "basic_salary": Decimal("0"),
            "housing_allowance": Decimal("0"),
            "other_earnings": Decimal("0"),
            "deductions": Decimal("0"),
        }
        needs_wps_breakdown = channel == BankExportChannel.WPS or bool(
            template and {"basic_salary", "housing_allowance", "other_earnings", "deductions"}.intersection(template.columns)
        )
        template_columns = set(template.columns) if template else set()
        if channel == BankExportChannel.WPS or "national_id" in template_columns:
            if not line.employee.national_id:
                blockers.append("National ID / Iqama is required by the selected payment channel/template.")
        if channel == BankExportChannel.WPS and profile and not profile.wps_enabled:
            blockers.append("Employee payment profile is not enabled for WPS.")
        if needs_wps_breakdown:
            breakdown, wps_blockers = _wps_breakdown(line)
            blockers.extend(wps_blockers)
        if template and profile:
            columns = set(template.columns)
            if "iban" in columns and profile.destination_type != PaymentDestination.IBAN:
                blockers.append("Selected export template requires an IBAN but this employee uses a salary card.")
            if "salary_card_number" in columns and profile.destination_type != PaymentDestination.SALARY_CARD:
                blockers.append("Selected export template requires a salary card number but this employee uses an IBAN.")
            if "bank_code" in columns and not profile.bank_code:
                blockers.append("Selected export template requires the employee bank code.")
        if not blockers:
            ready_count += 1
        rows.append({"line": line, "profile": profile, "breakdown": breakdown, "blockers": blockers})
    return {
        "ready": not company_blockers and ready_count == len(rows) and bool(rows),
        "company_blockers": company_blockers,
        "rows": rows,
        "ready_count": ready_count,
        "blocked_count": len(rows) - ready_count,
        "employee_count": len(rows),
    }


def _batch_snapshot_payload(batch: SalaryPaymentBatch) -> dict[str, object]:
    rows = list(SalaryPaymentRow.objects.for_company(batch.company).filter(batch=batch).order_by("employee_number", "id"))
    return {
        "run_id": str(batch.run_id),
        "run_snapshot": batch.run.snapshot_fingerprint,
        "reference": batch.reference,
        "channel": batch.channel,
        "template": {
            "code": batch.template_code,
            "name": batch.template_name,
            "delimiter": batch.delimiter,
            "encoding": batch.encoding,
            "include_header": batch.include_header,
            "columns": batch.columns,
            "headers": batch.headers,
            "result_columns": batch.result_columns,
        },
        "employer": {
            "identifier": batch.employer_identifier,
            "bank_name": batch.employer_bank_name,
            "bank_code": batch.employer_bank_code,
            "iban": batch.employer_iban,
            "customer_reference": batch.bank_customer_reference,
        },
        "rows": [
            {
                "run_line_id": str(row.run_line_id),
                "employee_id": str(row.employee_id),
                "employee_number": row.employee_number,
                "employee_name": row.employee_name,
                "national_id": row.national_id,
                "destination_type": row.destination_type,
                "account_holder_name": row.account_holder_name,
                "bank_name": row.bank_name,
                "bank_code": row.bank_code,
                "destination": row.iban if row.destination_type == PaymentDestination.IBAN else row.salary_card_number,
                "amount": str(row.amount),
                "basic_salary": str(row.basic_salary),
                "housing_allowance": str(row.housing_allowance),
                "other_earnings": str(row.other_earnings),
                "deductions": str(row.deductions),
            }
            for row in rows
        ],
    }


def _hash_batch_snapshot(batch: SalaryPaymentBatch) -> str:
    raw = json.dumps(_batch_snapshot_payload(batch), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _verify_batch_snapshot(batch: SalaryPaymentBatch) -> None:
    if not batch.source_fingerprint or _hash_batch_snapshot(batch) != batch.source_fingerprint:
        raise ValidationError({"batch": "Salary payment batch snapshot integrity check failed."})


@transaction.atomic
def prepare_salary_payment_batch(
    *,
    actor_membership: CompanyMembership,
    period_start: date,
    channel: str,
    template_id,
    note: str = "",
    request: HttpRequest | None = None,
) -> SalaryPaymentBatch:
    _require_internal_edit(actor_membership)
    company = actor_membership.company
    run = verify_payroll_run_integrity(company=company, period_start=period_start, verify_source=False)
    run = PayrollRun.objects.select_for_update().for_company(company).get(pk=run.pk)
    if run.status != PayrollRunStatus.APPROVED:
        raise ValidationError({"payroll": "Only an Approved payroll run can create a new salary payment batch."})
    template = BankExportTemplate.objects.select_for_update().for_company(company).get(pk=template_id, is_active=True)
    if template.channel != channel:
        raise ValidationError({"template": "Export template channel does not match the requested payment channel."})
    readiness = payment_readiness(company=company, run=run, channel=channel, template=template)
    if readiness["company_blockers"]:
        raise ValidationError({"payment_settings": list(readiness["company_blockers"])})
    blocked = [f"{item['line'].employee_number} · {reason}" for item in readiness["rows"] for reason in item["blockers"]]
    if blocked:
        raise ValidationError({"employees": blocked})
    if not readiness["rows"]:
        raise ValidationError({"payroll": "Approved payroll does not contain any payable employee rows."})

    settings_row = CompanySalaryPaymentSettings.objects.for_company(company).first()
    prefix = "WPS-" if channel == BankExportChannel.WPS else "BANK-"
    reference = allocate_number(company=company, key=f"internal.salary-payment.{channel}", prefix=prefix, padding=6)
    batch = SalaryPaymentBatch(
        company=company,
        run=run,
        reference=reference,
        channel=channel,
        export_template=template,
        template_code=template.code,
        template_name=template.name,
        delimiter=template.delimiter,
        encoding=template.encoding,
        include_header=template.include_header,
        columns=list(template.columns),
        headers=list(template.headers),
        result_columns=dict(template.result_columns),
        status=SalaryPaymentBatchStatus.PREPARED,
        employee_count=len(readiness["rows"]),
        total_amount=_money(run.total_net),
        paid_amount=Decimal("0"),
        source_fingerprint="pending",
        employer_identifier=settings_row.employer_identifier if settings_row else "",
        employer_bank_name=settings_row.employer_bank_name if settings_row else "",
        employer_bank_code=settings_row.employer_bank_code if settings_row else "",
        employer_iban=settings_row.employer_iban if settings_row else "",
        bank_customer_reference=settings_row.bank_customer_reference if settings_row else "",
        prepared_at=timezone.now(),
        prepared_by=actor_membership.user,
        note=note,
    )
    batch.full_clean()
    batch.save()
    for item in readiness["rows"]:
        line: PayrollRunLine = item["line"]
        profile: EmployeePaymentProfile = item["profile"]
        if channel == BankExportChannel.WPS or {"basic_salary", "housing_allowance", "other_earnings", "deductions"}.intersection(template.columns):
            breakdown, _ = _wps_breakdown(line)
        else:
            breakdown = {
                "basic_salary": line.basic,
                "housing_allowance": Decimal("0"),
                "other_earnings": _money(line.gross - line.basic),
                "deductions": _money(line.total_deductions),
            }
        row = SalaryPaymentRow(
            company=company,
            batch=batch,
            run_line=line,
            employee=line.employee,
            claim_active=True,
            employee_number=line.employee_number,
            employee_name=line.employee_name,
            national_id=line.employee.national_id,
            destination_type=profile.destination_type,
            account_holder_name=profile.account_holder_name,
            bank_name=profile.bank_name,
            bank_code=profile.bank_code,
            iban=profile.iban,
            salary_card_number=profile.salary_card_number,
            amount=line.net,
            basic_salary=breakdown["basic_salary"],
            housing_allowance=breakdown["housing_allowance"],
            other_earnings=breakdown["other_earnings"],
            deductions=breakdown["deductions"],
        )
        row.full_clean()
        row.save()
    batch.source_fingerprint = _hash_batch_snapshot(batch)
    batch.save(update_fields=("source_fingerprint", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.prepared",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        after={"reference": batch.reference, "channel": batch.channel, "employee_count": batch.employee_count, "total_amount": str(batch.total_amount), "template": batch.template_code},
        metadata={"payroll_run_id": str(run.pk), "period": run.period_start.isoformat()},
        request=request,
    )
    return batch


def _delimiter_char(value: str) -> str:
    return {BankExportDelimiter.COMMA: ",", BankExportDelimiter.TAB: "\t", BankExportDelimiter.SEMICOLON: ";"}[value]


def _export_value(batch: SalaryPaymentBatch, row: SalaryPaymentRow, key: str) -> str:
    values: dict[str, object] = {
        "employee_number": row.employee_number,
        "employee_name": row.employee_name,
        "national_id": row.national_id,
        "bank_name": row.bank_name,
        "bank_code": row.bank_code,
        "iban": row.iban,
        "salary_card_number": row.salary_card_number,
        "account_holder_name": row.account_holder_name,
        "basic_salary": row.basic_salary,
        "housing_allowance": row.housing_allowance,
        "other_earnings": row.other_earnings,
        "deductions": row.deductions,
        "net_salary": row.amount,
        "transaction_reference": f"{batch.reference}-{row.employee_number}",
        "period_start": batch.run.period_start.isoformat(),
        "period_end": batch.run.period_end.isoformat(),
        "employer_identifier": batch.employer_identifier,
        "employer_bank_name": batch.employer_bank_name,
        "employer_bank_code": batch.employer_bank_code,
        "employer_iban": batch.employer_iban,
        "bank_customer_reference": batch.bank_customer_reference,
    }
    value = values[key]
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value or "")


@transaction.atomic
def export_salary_payment_batch(
    *, actor_membership: CompanyMembership, batch_id, request: HttpRequest | None = None
) -> tuple[SalaryPaymentBatch, bytes, str, str]:
    _require_pay(actor_membership)
    company = actor_membership.company
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).select_related("run").get(pk=batch_id)
    if batch.status in {SalaryPaymentBatchStatus.CANCELLED, SalaryPaymentBatchStatus.CLOSED}:
        raise ValidationError({"batch": f"A {batch.get_status_display()} batch cannot be exported."})
    verify_payroll_run_integrity(company=company, period_start=batch.run.period_start, verify_source=False)
    _verify_batch_snapshot(batch)
    rows = list(SalaryPaymentRow.objects.select_for_update().for_company(company).filter(batch=batch).order_by("employee_number"))
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=_delimiter_char(batch.delimiter), lineterminator="\n")
    if batch.include_header:
        writer.writerow(batch.headers)
    for row in rows:
        writer.writerow([_export_value(batch, row, key) for key in batch.columns])
    data = output.getvalue().encode(batch.encoding)
    digest = hashlib.sha256(data).hexdigest()
    before = {"status": batch.status, "last_export_sha256": batch.last_export_sha256}
    if batch.status == SalaryPaymentBatchStatus.PREPARED:
        batch.status = SalaryPaymentBatchStatus.EXPORTED
    batch.exported_at = timezone.now()
    batch.exported_by = actor_membership.user
    batch.last_export_sha256 = digest
    batch.full_clean()
    batch.save()
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.exported",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        before=before,
        after={"status": batch.status, "sha256": digest, "bytes": len(data), "template": batch.template_code},
        request=request,
    )
    extension = "tsv" if batch.delimiter == BankExportDelimiter.TAB else "csv"
    filename = f"{batch.reference}-{batch.run.period_start:%Y-%m}.{extension}"
    content_type = "text/tab-separated-values" if extension == "tsv" else "text/csv"
    return batch, data, filename, content_type


def _refresh_batch_locked(batch: SalaryPaymentBatch) -> SalaryPaymentBatch:
    rows = list(SalaryPaymentRow.objects.select_for_update().for_company(batch.company).filter(batch=batch))
    paid = sum((row.amount for row in rows if row.status == SalaryPaymentRowStatus.PAID), Decimal("0"))
    batch.paid_amount = _money(paid)
    statuses = {row.status for row in rows}
    if rows and statuses == {SalaryPaymentRowStatus.PAID}:
        batch.status = SalaryPaymentBatchStatus.PAID
        batch.completed_at = batch.completed_at or timezone.now()
    elif statuses & {SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED}:
        batch.status = SalaryPaymentBatchStatus.ATTENTION
        batch.completed_at = None
    elif SalaryPaymentRowStatus.PROCESSING in statuses:
        batch.status = SalaryPaymentBatchStatus.PARTIALLY_PAID if SalaryPaymentRowStatus.PAID in statuses else SalaryPaymentBatchStatus.PROCESSING
        batch.completed_at = None
    elif SalaryPaymentRowStatus.PAID in statuses:
        batch.status = SalaryPaymentBatchStatus.PARTIALLY_PAID
        batch.completed_at = None
    batch.full_clean()
    batch.save()
    run = PayrollRun.objects.select_for_update().for_company(batch.company).get(pk=batch.run_id)
    if batch.status == SalaryPaymentBatchStatus.PAID:
        # One active payment row per payroll line ensures this means every payroll line in the batch is paid.
        run.status = PayrollRunStatus.PAID
    elif batch.status not in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED, SalaryPaymentBatchStatus.CANCELLED}:
        run.status = PayrollRunStatus.PAYMENT_PROCESSING
    run.save(update_fields=("status", "updated_at"))
    return batch


@transaction.atomic
def start_salary_payment_batch(
    *, actor_membership: CompanyMembership, batch_id, request: HttpRequest | None = None
) -> SalaryPaymentBatch:
    _require_pay(actor_membership)
    company = actor_membership.company
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).select_related("run").get(pk=batch_id)
    if batch.status not in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:
        raise ValidationError({"batch": "Only a Prepared or Exported batch can start payment processing."})
    verify_payroll_run_integrity(company=company, period_start=batch.run.period_start, verify_source=False)
    _verify_batch_snapshot(batch)
    rows = list(SalaryPaymentRow.objects.select_for_update().for_company(company).filter(batch=batch, claim_active=True))
    if not rows:
        raise ValidationError({"batch": "Payment batch has no active salary rows."})
    now = timezone.now()
    for row in rows:
        if row.status != SalaryPaymentRowStatus.PENDING:
            continue
        row.attempt_count += 1
        row.status = SalaryPaymentRowStatus.PROCESSING
        row.failure_reason = ""
        row.transaction_reference = ""
        row.last_result_at = None
        row.save()
        SalaryPaymentAttempt.objects.create(
            company=company,
            row=row,
            attempt_number=row.attempt_count,
            status=SalaryPaymentAttemptStatus.PROCESSING,
            started_at=now,
            started_by=actor_membership.user,
        )
    batch.processing_at = batch.processing_at or now
    batch.processing_by = actor_membership.user
    batch.status = SalaryPaymentBatchStatus.PROCESSING
    batch.full_clean()
    batch.save()
    run = PayrollRun.objects.select_for_update().for_company(company).get(pk=batch.run_id)
    run.status = PayrollRunStatus.PAYMENT_PROCESSING
    run.save(update_fields=("status", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.processing_started",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        after={"status": batch.status, "attempted_rows": len(rows)},
        request=request,
    )
    return batch


def _normalize_result_status(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_").replace("-", "_")
    mapping = {
        "paid": SalaryPaymentRowStatus.PAID,
        "success": SalaryPaymentRowStatus.PAID,
        "successful": SalaryPaymentRowStatus.PAID,
        "failed": SalaryPaymentRowStatus.FAILED,
        "rejected": SalaryPaymentRowStatus.FAILED,
        "reversed": SalaryPaymentRowStatus.REVERSED,
        "returned": SalaryPaymentRowStatus.REVERSED,
        "processing": SalaryPaymentRowStatus.PROCESSING,
        "pending": SalaryPaymentRowStatus.PROCESSING,
    }
    if normalized not in mapping:
        raise ValidationError({"status": f"Unsupported bank result status: {value}."})
    return mapping[normalized]


def _parse_result_csv(content: str, result_columns: dict[str, str] | None = None) -> list[dict[str, str]]:
    if not content.strip():
        raise ValidationError({"file": "Bank result file is empty."})
    sample = content[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise ValidationError({"file": "Bank result file must contain a header row."})
    field_lookup = {str(name).strip().casefold(): name for name in reader.fieldnames}
    configured = {str(key): str(value).strip() for key, value in (result_columns or {}).items() if str(value).strip()}
    if configured:
        missing = [value for value in configured.values() if value.casefold() not in field_lookup]
        if missing:
            raise ValidationError({"file": f"Result file is missing configured header: {missing[0]}."})
        employee_key = field_lookup.get(configured.get("employee", "").casefold())
        status_key = field_lookup.get(configured.get("status", "").casefold())
        reference_key = field_lookup.get(configured.get("reference", "").casefold()) if configured.get("reference") else None
        reason_key = field_lookup.get(configured.get("reason", "").casefold()) if configured.get("reason") else None
    else:
        aliases = {str(name).strip().lower().replace(" ", "_"): name for name in reader.fieldnames}
        employee_key = aliases.get("employee_id") or aliases.get("employee_number") or aliases.get("employee")
        status_key = aliases.get("status") or aliases.get("payment_status")
        reference_key = aliases.get("reference") or aliases.get("transaction_reference") or aliases.get("bank_reference")
        reason_key = aliases.get("reason") or aliases.get("failure_reason") or aliases.get("message")
    if not employee_key or not status_key:
        raise ValidationError({"file": "Result file requires Employee ID and Status columns."})
    rows: list[dict[str, str]] = []
    for index, raw in enumerate(reader, start=2):
        employee = str(raw.get(employee_key) or "").strip()
        status = str(raw.get(status_key) or "").strip()
        if not employee and not status:
            continue
        if not employee or not status:
            raise ValidationError({"file": f"Line {index} requires both Employee ID and Status."})
        rows.append({
            "employee": employee,
            "status": status,
            "reference": str(raw.get(reference_key) or "").strip() if reference_key else "",
            "reason": str(raw.get(reason_key) or "").strip() if reason_key else "",
            "line": str(index),
        })
    if not rows:
        raise ValidationError({"file": "Bank result file contains no payment rows."})
    return rows


@transaction.atomic
def import_salary_payment_results(
    *,
    actor_membership: CompanyMembership,
    batch_id,
    file_name: str,
    content: str,
    request: HttpRequest | None = None,
) -> tuple[SalaryPaymentBatch, SalaryPaymentResultImport, list[str]]:
    _require_pay(actor_membership)
    if len(content.encode("utf-8")) > 2 * 1024 * 1024:
        raise ValidationError({"file": "Bank result file exceeds the 2 MiB reconciliation limit."})
    company = actor_membership.company
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).select_related("run").get(pk=batch_id)
    if batch.status in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:
        raise ValidationError({"batch": "Start payment processing before importing bank results."})
    if batch.status in {SalaryPaymentBatchStatus.CANCELLED, SalaryPaymentBatchStatus.CLOSED}:
        raise ValidationError({"batch": f"A {batch.get_status_display()} batch cannot accept reconciliation results."})
    _verify_batch_snapshot(batch)
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if SalaryPaymentResultImport.objects.for_company(company).filter(batch=batch, content_sha256=digest).exists():
        raise ValidationError({"file": "This bank result file was already imported for the batch."})
    parsed = _parse_result_csv(content, batch.result_columns)
    rows = list(SalaryPaymentRow.objects.select_for_update().for_company(company).filter(batch=batch))
    by_employee = {row.employee_number.upper(): row for row in rows}
    errors: list[str] = []
    updated = 0
    seen: set[str] = set()
    now = timezone.now()
    for item in parsed:
        key = item["employee"].upper()
        row = by_employee.get(key)
        if row is None:
            errors.append(f"Line {item['line']}: employee {item['employee']} is not in this batch.")
            continue
        if key in seen:
            errors.append(f"Line {item['line']}: duplicate employee {item['employee']} in result file.")
            continue
        seen.add(key)
        try:
            new_status = _normalize_result_status(item["status"])
        except ValidationError as exc:
            errors.append(f"Line {item['line']}: {exc.messages[0]}")
            continue
        if row.attempt_count == 0:
            errors.append(f"Line {item['line']}: employee {item['employee']} has no started payment attempt.")
            continue
        attempt = SalaryPaymentAttempt.objects.select_for_update().for_company(company).get(row=row, attempt_number=row.attempt_count)
        if new_status == SalaryPaymentRowStatus.PAID and not item["reference"]:
            errors.append(f"Line {item['line']}: Paid result requires a transaction reference.")
            continue
        if new_status in {SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED} and not item["reason"]:
            errors.append(f"Line {item['line']}: {new_status.title()} result requires a reason.")
            continue
        row.status = new_status
        row.transaction_reference = item["reference"].strip().upper()
        row.failure_reason = item["reason"].strip()
        row.last_result_at = now
        if new_status == SalaryPaymentRowStatus.PAID:
            row.paid_at = now
            attempt.status = SalaryPaymentAttemptStatus.PAID
        elif new_status == SalaryPaymentRowStatus.FAILED:
            row.paid_at = None
            attempt.status = SalaryPaymentAttemptStatus.FAILED
        elif new_status == SalaryPaymentRowStatus.REVERSED:
            row.paid_at = None
            attempt.status = SalaryPaymentAttemptStatus.REVERSED
        else:
            attempt.status = SalaryPaymentAttemptStatus.PROCESSING
        row.save()
        attempt.transaction_reference = row.transaction_reference
        attempt.failure_reason = row.failure_reason
        attempt.finished_at = None if attempt.status == SalaryPaymentAttemptStatus.PROCESSING else now
        attempt.full_clean()
        attempt.save()
        updated += 1
    result_import = SalaryPaymentResultImport(
        company=company,
        batch=batch,
        file_name=file_name,
        content_sha256=digest,
        updated_rows=updated,
        error_count=len(errors),
        imported_at=now,
        imported_by=actor_membership.user,
    )
    result_import.full_clean()
    result_import.save()
    _refresh_batch_locked(batch)
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_results.imported",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        after={"status": batch.status, "updated_rows": updated, "errors": len(errors), "paid_amount": str(batch.paid_amount)},
        metadata={"file_name": result_import.file_name, "sha256": digest, "errors": errors[:50]},
        request=request,
    )
    return batch, result_import, errors


@transaction.atomic
def retry_salary_payment_row(
    *, actor_membership: CompanyMembership, row_id, request: HttpRequest | None = None
) -> SalaryPaymentRow:
    _require_pay(actor_membership)
    company = actor_membership.company
    row = SalaryPaymentRow.objects.select_for_update().for_company(company).select_related("batch").get(pk=row_id)
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).get(pk=row.batch_id)
    if batch.status == SalaryPaymentBatchStatus.CLOSED:
        raise ValidationError({"batch": "Reopen a Closed batch before retrying a salary payment."})
    if row.status not in {SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED}:
        raise ValidationError({"payment": "Only Failed or Reversed salary rows can be retried."})
    before = {"status": row.status, "attempt_count": row.attempt_count, "reference": row.transaction_reference}
    row.attempt_count += 1
    row.status = SalaryPaymentRowStatus.PROCESSING
    row.transaction_reference = ""
    row.failure_reason = ""
    row.paid_at = None
    row.last_result_at = None
    row.save()
    SalaryPaymentAttempt.objects.create(
        company=company,
        row=row,
        attempt_number=row.attempt_count,
        status=SalaryPaymentAttemptStatus.PROCESSING,
        started_at=timezone.now(),
        started_by=actor_membership.user,
    )
    _refresh_batch_locked(batch)
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_row.retried",
        object_type="internal_payroll.SalaryPaymentRow",
        object_id=row.pk,
        object_label=f"{batch.reference} · {row.employee_number}",
        actor_membership=actor_membership,
        before=before,
        after={"status": row.status, "attempt_count": row.attempt_count},
        request=request,
    )
    return row


@transaction.atomic
def cancel_salary_payment_batch(
    *, actor_membership: CompanyMembership, batch_id, reason: str, request: HttpRequest | None = None
) -> SalaryPaymentBatch:
    _require_pay(actor_membership)
    company = actor_membership.company
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": "Cancellation reason is required."})
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).get(pk=batch_id)
    if batch.status not in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:
        raise ValidationError({"batch": "Only a Prepared or Exported batch can be cancelled."})
    rows = list(SalaryPaymentRow.objects.select_for_update().for_company(company).filter(batch=batch))
    for row in rows:
        row.status = SalaryPaymentRowStatus.CANCELLED
        row.claim_active = False
        row.save(update_fields=("status", "claim_active", "updated_at"))
    before = {"status": batch.status}
    batch.status = SalaryPaymentBatchStatus.CANCELLED
    batch.note = reason
    batch.save(update_fields=("status", "note", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.cancelled",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        before=before,
        after={"status": batch.status},
        metadata={"reason": reason},
        request=request,
    )
    return batch


@transaction.atomic
def close_salary_payment_batch(
    *, actor_membership: CompanyMembership, batch_id, request: HttpRequest | None = None
) -> SalaryPaymentBatch:
    _require_pay(actor_membership)
    company = actor_membership.company
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).get(pk=batch_id)
    _refresh_batch_locked(batch)
    if batch.status != SalaryPaymentBatchStatus.PAID:
        raise ValidationError({"batch": "Only a fully Paid salary payment batch can be closed."})
    batch.status = SalaryPaymentBatchStatus.CLOSED
    batch.closed_at = timezone.now()
    batch.closed_by = actor_membership.user
    batch.full_clean()
    batch.save()
    run = PayrollRun.objects.select_for_update().for_company(company).get(pk=batch.run_id)
    run.status = PayrollRunStatus.CLOSED
    run.save(update_fields=("status", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.closed",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        after={"status": batch.status, "paid_amount": str(batch.paid_amount)},
        request=request,
    )
    return batch


@transaction.atomic
def reopen_salary_payment_batch(
    *, actor_membership: CompanyMembership, batch_id, reason: str, request: HttpRequest | None = None
) -> SalaryPaymentBatch:
    _require_pay(actor_membership)
    company = actor_membership.company
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required to reopen a closed payment batch."})
    batch = SalaryPaymentBatch.objects.select_for_update().for_company(company).get(pk=batch_id)
    if batch.status != SalaryPaymentBatchStatus.CLOSED:
        raise ValidationError({"batch": "Only a Closed payment batch can be reopened."})
    batch.status = SalaryPaymentBatchStatus.PAID
    batch.closed_at = None
    batch.closed_by = None
    batch.save(update_fields=("status", "closed_at", "closed_by", "updated_at"))
    run = PayrollRun.objects.select_for_update().for_company(company).get(pk=batch.run_id)
    run.status = PayrollRunStatus.PAID
    run.save(update_fields=("status", "updated_at"))
    record_audit_event(
        company=company,
        area=AuditArea.INTERNAL,
        action="internal.salary_payment_batch.reopened",
        object_type="internal_payroll.SalaryPaymentBatch",
        object_id=batch.pk,
        object_label=batch.reference,
        actor_membership=actor_membership,
        before={"status": SalaryPaymentBatchStatus.CLOSED},
        after={"status": batch.status},
        metadata={"reason": reason},
        request=request,
    )
    return batch
