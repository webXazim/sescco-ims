from __future__ import annotations

from datetime import date

from apps.accounts.permissions import membership_can_edit, membership_has_capability
from apps.accounts.roles import Capability, Workspace
from apps.internal_payroll.models import (
    BankExportChannel,
    BankExportTemplate,
    CompanySalaryPaymentSettings,
    EmployeePaymentProfile,
    PayrollRun,
    PayrollRunStatus,
    SalaryPaymentBatch,
    SalaryPaymentRow,
)
from apps.internal_payroll.services.attendance import month_bounds
from apps.internal_payroll.services.payment import _masked, payment_readiness


def serialize_payment_profile(profile: EmployeePaymentProfile) -> dict[str, object]:
    destination = profile.iban if profile.destination_type == "iban" else profile.salary_card_number
    return {
        "id": str(profile.pk),
        "employeeId": str(profile.employee_id),
        "destinationType": profile.destination_type,
        "destinationLabel": profile.get_destination_type_display(),
        "accountHolderName": profile.account_holder_name,
        "bankName": profile.bank_name,
        "bankCode": profile.bank_code,
        "destinationMasked": _masked(destination),
        "ibanMasked": _masked(profile.iban),
        "salaryCardMasked": _masked(profile.salary_card_number),
        "wpsEnabled": profile.wps_enabled,
        "active": profile.is_active,
        "verifiedAt": profile.verified_at.isoformat() if profile.verified_at else None,
    }


def serialize_payment_settings(row: CompanySalaryPaymentSettings | None) -> dict[str, object]:
    return {
        "id": str(row.pk) if row else None,
        "employerIdentifier": row.employer_identifier if row else "",
        "employerBankName": row.employer_bank_name if row else "",
        "employerBankCode": row.employer_bank_code if row else "",
        "employerIbanMasked": _masked(row.employer_iban) if row else "",
        "hasEmployerIban": bool(row and row.employer_iban),
        "bankCustomerReference": row.bank_customer_reference if row else "",
    }


def serialize_export_template(template: BankExportTemplate) -> dict[str, object]:
    return {
        "id": str(template.pk),
        "code": template.code,
        "name": template.name,
        "channel": template.channel,
        "channelLabel": template.get_channel_display(),
        "delimiter": template.delimiter,
        "encoding": template.encoding,
        "includeHeader": template.include_header,
        "columns": list(template.columns),
        "headers": list(template.headers),
        "resultColumns": dict(template.result_columns),
        "active": template.is_active,
        "status": "Archived" if template.archived_at else ("Active" if template.is_active else "Inactive"),
        "archived": bool(template.archived_at),
        "archivedAt": template.archived_at.isoformat() if template.archived_at else None,
        "archivedReason": template.archived_reason,
    }


def serialize_payment_row(row: SalaryPaymentRow) -> dict[str, object]:
    return {
        "id": str(row.pk),
        "employeeId": str(row.employee_id),
        "employeeCode": row.employee_number,
        "name": row.employee_name,
        "nationalId": row.national_id,
        "address": row.employee_address,
        "destinationType": row.destination_type,
        "bank": row.bank_name,
        "bankCode": row.bank_code,
        "account": _masked(row.iban if row.destination_type == "iban" else row.salary_card_number),
        "amount": str(row.amount),
        "basicSalary": str(row.basic_salary),
        "housingAllowance": str(row.housing_allowance),
        "otherEarnings": str(row.other_earnings),
        "deductions": str(row.deductions),
        "statusValue": row.status,
        "status": row.get_status_display(),
        "reference": row.transaction_reference,
        "failureReason": row.failure_reason,
        "attempts": row.attempt_count,
        "paidAt": row.paid_at.isoformat() if row.paid_at else None,
        "lastResultAt": row.last_result_at.isoformat() if row.last_result_at else None,
    }


def serialize_payment_batch(batch: SalaryPaymentBatch) -> dict[str, object]:
    rows = getattr(batch, "payment_rows", None)
    if rows is None:
        rows = list(batch.rows.all().order_by("employee_number"))
    return {
        "id": str(batch.pk),
        "reference": batch.reference,
        "runId": str(batch.run_id),
        "period": f"{batch.run.period_start:%B %Y}",
        "periodKey": f"{batch.run.period_start:%Y-%m}",
        "channelValue": batch.channel,
        "channel": batch.get_channel_display(),
        "templateId": str(batch.export_template_id) if batch.export_template_id else None,
        "templateCode": batch.template_code,
        "templateName": batch.template_name,
        "statusValue": batch.status,
        "status": batch.get_status_display(),
        "employeeCount": batch.employee_count,
        "total": str(batch.total_amount),
        "paidAmount": str(batch.paid_amount),
        "createdAt": batch.prepared_at.isoformat(),
        "exportedAt": batch.exported_at.isoformat() if batch.exported_at else None,
        "processingAt": batch.processing_at.isoformat() if batch.processing_at else None,
        "completedAt": batch.completed_at.isoformat() if batch.completed_at else None,
        "closedAt": batch.closed_at.isoformat() if batch.closed_at else None,
        "lastExportSha256": batch.last_export_sha256,
        "rows": [serialize_payment_row(item) for item in rows],
    }


def _serialize_readiness(*, company, run: PayrollRun | None, channel: str, template: BankExportTemplate | None = None) -> dict[str, object]:
    if run is None:
        return {"ready": False, "companyBlockers": ["Approved payroll is not available."], "readyCount": 0, "blockedCount": 0, "employees": []}
    result = payment_readiness(company=company, run=run, channel=channel, template=template)
    company_blockers = list(result["company_blockers"])
    if run.status not in {PayrollRunStatus.APPROVED, PayrollRunStatus.PAYMENT_PROCESSING, PayrollRunStatus.PAID, PayrollRunStatus.CLOSED}:
        company_blockers.insert(0, f"Payroll must be Approved before a salary payment batch can be prepared. Current status: {run.get_status_display()}.")
    employees: list[dict[str, object]] = []
    for item in result["rows"]:
        line = item["line"]
        profile = item["profile"]
        employees.append({
            "employeeId": str(line.employee_id),
            "employeeCode": line.employee_number,
            "name": line.employee_name,
            "branch": line.branch_name,
            "department": line.department_name,
            "position": line.position,
            "netSalary": str(line.net),
            "basicSalary": str(item["breakdown"]["basic_salary"]),
            "housingAllowance": str(item["breakdown"]["housing_allowance"]),
            "otherEarnings": str(item["breakdown"]["other_earnings"]),
            "deductions": str(item["breakdown"]["deductions"]),
            "bank": profile.bank_name if profile else "",
            "account": _masked((profile.iban if profile.destination_type == "iban" else profile.salary_card_number) if profile else ""),
            "status": "Ready" if not item["blockers"] else "Blocked",
            "blockers": list(item["blockers"]),
        })
    return {
        "ready": result["ready"] and not company_blockers,
        "companyBlockers": company_blockers,
        "readyCount": result["ready_count"],
        "blockedCount": result["blocked_count"],
        "employees": employees,
    }


def salary_payment_context(*, company, period_start: date, membership=None, bank_template_id=None, wps_template_id=None) -> dict[str, object]:
    start, _end = month_bounds(period_start)
    run = PayrollRun.objects.for_company(company).filter(period_start=start).first()
    profiles = list(EmployeePaymentProfile.objects.for_company(company).select_related("employee", "verified_by").order_by("employee__employee_number"))
    templates = list(BankExportTemplate.objects.for_company(company).order_by("channel", "name"))
    batches_qs = SalaryPaymentBatch.objects.for_company(company).filter(run__period_start=start).select_related("run", "export_template").order_by("-prepared_at")
    rows_qs = SalaryPaymentRow.objects.for_company(company).filter(batch_id__in=batches_qs.values_list("id", flat=True)).order_by("employee_number")
    rows_by_batch: dict[str, list[SalaryPaymentRow]] = {}
    for row in rows_qs:
        rows_by_batch.setdefault(str(row.batch_id), []).append(row)
    batches = list(batches_qs)
    for batch in batches:
        batch.payment_rows = rows_by_batch.get(str(batch.pk), [])
    settings_row = CompanySalaryPaymentSettings.objects.for_company(company).first()
    active_bank_template = next((item for item in templates if item.is_active and not item.archived_at and item.channel == BankExportChannel.BANK_CSV and (bank_template_id is None or str(item.pk) == str(bank_template_id))), None)
    if active_bank_template is None and bank_template_id is None:
        active_bank_template = next((item for item in templates if item.is_active and not item.archived_at and item.channel == BankExportChannel.BANK_CSV), None)
    active_wps_template = next((item for item in templates if item.is_active and not item.archived_at and item.channel == BankExportChannel.WPS and (wps_template_id is None or str(item.pk) == str(wps_template_id))), None)
    if active_wps_template is None and wps_template_id is None:
        active_wps_template = next((item for item in templates if item.is_active and not item.archived_at and item.channel == BankExportChannel.WPS), None)
    return {
        "period": f"{start:%Y-%m}",
        "payrollStatus": run.status if run else None,
        "payrollStatusLabel": run.get_status_display() if run else "Not calculated",
        "payrollRunId": str(run.pk) if run else None,
        "settings": serialize_payment_settings(settings_row),
        "profiles": {str(item.employee_id): serialize_payment_profile(item) for item in profiles},
        "templates": [serialize_export_template(item) for item in templates],
        "batches": [serialize_payment_batch(item) for item in batches],
        "bankReadinessTemplateId": str(active_bank_template.pk) if active_bank_template else None,
        "wpsReadinessTemplateId": str(active_wps_template.pk) if active_wps_template else None,
        "bankReadiness": _serialize_readiness(company=company, run=run, channel=BankExportChannel.BANK_CSV, template=active_bank_template),
        "wpsReadiness": _serialize_readiness(company=company, run=run, channel=BankExportChannel.WPS, template=active_wps_template),
        "canEditSetup": bool(membership and membership_can_edit(membership, Workspace.INTERNAL)),
        "canPay": bool(membership and membership_has_capability(membership, Capability.PAY)),
    }
