from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Q, Sum

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
    SalaryPaymentBatchStatus,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
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


def serialize_payment_row(row: SalaryPaymentRow, *, can_pay: bool = False) -> dict[str, object]:
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
        "canRetry": bool(can_pay and row.status in {SalaryPaymentRowStatus.FAILED, SalaryPaymentRowStatus.REVERSED}),
    }


def serialize_payment_batch(batch: SalaryPaymentBatch, *, membership=None, include_rows: bool = True) -> dict[str, object]:
    rows = []
    if include_rows:
        rows = getattr(batch, "payment_rows", None)
        if rows is None:
            rows = list(batch.rows.all().order_by("employee_number"))
    can_pay = bool(membership and membership_has_capability(membership, Capability.PAY))
    allowed_actions: list[str] = []
    if can_pay and batch.status not in {SalaryPaymentBatchStatus.CANCELLED, SalaryPaymentBatchStatus.CLOSED}:
        allowed_actions.append("export")
    if can_pay and batch.status in {SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED}:
        allowed_actions.extend(["start", "cancel"])
    if can_pay and batch.status in {SalaryPaymentBatchStatus.PROCESSING, SalaryPaymentBatchStatus.PARTIALLY_PAID, SalaryPaymentBatchStatus.ATTENTION}:
        allowed_actions.append("import_results")
    if can_pay and batch.status == SalaryPaymentBatchStatus.PAID:
        allowed_actions.append("close")
    if can_pay and batch.status == SalaryPaymentBatchStatus.CLOSED:
        allowed_actions.append("reopen")
    next_action = next((item for item in ("start", "import_results", "close") if item in allowed_actions), None)
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
        "canPay": can_pay,
        "allowedActions": allowed_actions,
        "nextAction": next_action,
        "rows": [serialize_payment_row(item, can_pay=can_pay) for item in rows] if include_rows else [],
        "rowsDeferred": not include_rows,
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



PAYMENT_PAGE_SIZES = {25, 50, 100}
PAYMENT_READINESS_SCAN_CHUNK = 250


def _bounded_page(value, default: int = 1) -> int:
    try:
        return max(1, int(value or default))
    except (TypeError, ValueError):
        return default


def _bounded_page_size(value, default: int = 50) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed in PAYMENT_PAGE_SIZES else default


def _payment_templates(company) -> list[BankExportTemplate]:
    return list(BankExportTemplate.objects.for_company(company).order_by("channel", "name"))


def _active_template(templates: list[BankExportTemplate], *, channel: str, template_id=None) -> BankExportTemplate | None:
    if template_id:
        return next(
            (
                item
                for item in templates
                if str(item.pk) == str(template_id)
                and item.channel == channel
                and item.is_active
                and not item.archived_at
            ),
            None,
        )
    return next(
        (item for item in templates if item.channel == channel and item.is_active and not item.archived_at),
        None,
    )


def salary_payment_shell_context(
    *, company, period_start: date, membership=None, bank_template_id=None, wps_template_id=None
) -> dict[str, object]:
    """Compact salary-payment shell.

    Upgrade 1.0.75 deliberately excludes employee payment profiles, readiness rows and
    batch rows. Those high-cardinality records are requested through bounded page APIs.
    """
    start, _end = month_bounds(period_start)
    run = PayrollRun.objects.for_company(company).filter(period_start=start).first()
    templates = _payment_templates(company)
    batches = list(
        SalaryPaymentBatch.objects.for_company(company)
        .filter(run__period_start=start)
        .select_related("run", "export_template")
        .order_by("-prepared_at")
    )
    settings_row = CompanySalaryPaymentSettings.objects.for_company(company).first()
    active_bank_template = _active_template(
        templates, channel=BankExportChannel.BANK_CSV, template_id=bank_template_id
    )
    active_wps_template = _active_template(
        templates, channel=BankExportChannel.WPS, template_id=wps_template_id
    )
    return {
        "surface": "salary_payment_shell",
        "period": f"{start:%Y-%m}",
        "payrollStatus": run.status if run else None,
        "payrollStatusLabel": run.get_status_display() if run else "Not calculated",
        "payrollRunId": str(run.pk) if run else None,
        "settings": serialize_payment_settings(settings_row),
        "profiles": {},
        "profilesDeferred": True,
        "templates": [serialize_export_template(item) for item in templates],
        "batches": [serialize_payment_batch(item, membership=membership, include_rows=False) for item in batches],
        "bankReadinessTemplateId": str(active_bank_template.pk) if active_bank_template else None,
        "wpsReadinessTemplateId": str(active_wps_template.pk) if active_wps_template else None,
        "bankReadiness": {
            "deferred": True,
            "ready": False,
            "companyBlockers": [],
            "readyCount": 0,
            "blockedCount": 0,
            "employees": [],
        },
        "wpsReadiness": {
            "deferred": True,
            "ready": False,
            "companyBlockers": [],
            "readyCount": 0,
            "blockedCount": 0,
            "employees": [],
        },
        "canEditSetup": bool(membership and membership_can_edit(membership, Workspace.INTERNAL)),
        "canPay": bool(membership and membership_has_capability(membership, Capability.PAY)),
    }


def _serialize_readiness_item(item: dict[str, object], *, channel: str) -> dict[str, object]:
    line = item["line"]
    profile = item["profile"]
    blockers = list(item["blockers"])
    breakdown = item["breakdown"]
    return {
        "employeeId": str(line.employee_id),
        "employeeCode": line.employee_number,
        "name": line.employee_name,
        "branchId": str(line.branch_id_snapshot) if line.branch_id_snapshot else None,
        "branch": line.branch_name,
        "departmentId": str(line.department_id_snapshot) if line.department_id_snapshot else None,
        "department": line.department_name,
        "position": line.position,
        "nationalId": line.employee.national_id,
        "address": line.employee.address,
        "netSalary": str(line.net),
        "basicSalary": str(breakdown["basic_salary"]),
        "housingAllowance": str(breakdown["housing_allowance"]),
        "otherEarnings": str(breakdown["other_earnings"]),
        "deductions": str(breakdown["deductions"]),
        "bank": profile.bank_name if profile else "",
        "account": _masked(
            (profile.iban if profile.destination_type == "iban" else profile.salary_card_number)
            if profile
            else ""
        ),
        "status": "Ready" if not blockers else "Blocked",
        "blockers": blockers,
        "profile": serialize_payment_profile(profile) if profile else None,
        "channel": channel,
    }


def _readiness_candidate_queryset(*, company, run: PayrollRun, search: str = "", branch: str = ""):
    # run.lines is already scoped to one company-owned payroll run.
    qs = run.lines.filter(company=company, net__gt=0).select_related("employee").order_by("employee_number", "id")
    query = (search or "").strip()
    if query:
        qs = qs.filter(
            Q(employee_number__icontains=query)
            | Q(employee_name__icontains=query)
            | Q(branch_name__icontains=query)
            | Q(department_name__icontains=query)
            | Q(position__icontains=query)
            | Q(employee__national_id__icontains=query)
            | Q(employee__payment_profile__bank_name__icontains=query)
            | Q(employee__payment_profile__bank_code__icontains=query)
        ).distinct()
    branch_value = (branch or "").strip()
    if branch_value and branch_value.lower() not in {"all", "all branches"}:
        qs = qs.filter(branch_id_snapshot=branch_value)
    return qs


def salary_payment_readiness_page_context(
    *,
    company,
    period_start: date,
    channel: str,
    membership=None,
    template_id=None,
    page=1,
    page_size=50,
    search: str = "",
    status: str = "All",
    branch: str = "",
) -> dict[str, object]:
    """Return one server-authoritative readiness page with exact filtered totals.

    Readiness classification is scanned in bounded 250-employee chunks so the server
    never materializes a 2,000-profile/browser payload. Only the requested 25/50/100
    employee rows (and their payment profiles) are serialized to the client.
    """
    from apps.internal_payroll.services.payment import payment_readiness

    if channel not in BankExportChannel.values:
        raise ValueError("Unsupported salary payment channel.")
    start, _end = month_bounds(period_start)
    run = PayrollRun.objects.for_company(company).filter(period_start=start).first()
    templates = _payment_templates(company)
    template = _active_template(templates, channel=channel, template_id=template_id)
    bounded_page = _bounded_page(page)
    bounded_size = _bounded_page_size(page_size)
    normalized_status = (status or "All").strip().lower()
    if normalized_status not in {"all", "ready", "blocked"}:
        normalized_status = "all"

    if run is None:
        return {
            "surface": "salary_payment_readiness_page",
            "period": f"{start:%Y-%m}",
            "channel": channel,
            "templateId": str(template.pk) if template else None,
            "readiness": {
                "ready": False,
                "companyBlockers": ["Approved payroll is not available."],
                "readyCount": 0,
                "blockedCount": 0,
                "employeeCount": 0,
                "amount": "0.00",
                "readyAmount": "0.00",
                "employees": [],
            },
            "meta": {"page": 1, "pageSize": bounded_size, "count": 0, "totalPages": 1, "rangeStart": 0, "rangeEnd": 0},
        }

    candidate_ids = list(
        _readiness_candidate_queryset(company=company, run=run, search=search, branch=branch)
        .values_list("employee_id", flat=True)
    )
    company_blockers: list[str] = []
    classified: list[dict[str, object]] = []
    ready_count = 0
    blocked_count = 0
    total_amount = Decimal("0")
    ready_amount = Decimal("0")
    for offset in range(0, len(candidate_ids), PAYMENT_READINESS_SCAN_CHUNK):
        chunk_ids = candidate_ids[offset : offset + PAYMENT_READINESS_SCAN_CHUNK]
        chunk = payment_readiness(
            company=company, run=run, channel=channel, template=template, employee_ids=chunk_ids
        )
        if not company_blockers:
            company_blockers = list(chunk["company_blockers"])
        for item in chunk["rows"]:
            serialized = _serialize_readiness_item(item, channel=channel)
            total_amount += Decimal(serialized["netSalary"])
            if serialized["status"] == "Ready":
                ready_count += 1
                ready_amount += Decimal(serialized["netSalary"])
            else:
                blocked_count += 1
            if normalized_status == "all" or serialized["status"].lower() == normalized_status:
                classified.append(serialized)

    paginator = Paginator(classified, bounded_size)
    page_obj = paginator.get_page(bounded_page)
    count = paginator.count
    range_start = page_obj.start_index() if count else 0
    range_end = page_obj.end_index() if count else 0
    return {
        "surface": "salary_payment_readiness_page",
        "period": f"{start:%Y-%m}",
        "channel": channel,
        "templateId": str(template.pk) if template else None,
        "readiness": {
            "ready": bool(candidate_ids) and not company_blockers and blocked_count == 0,
            "companyBlockers": company_blockers,
            "readyCount": ready_count,
            "blockedCount": blocked_count,
            "employeeCount": ready_count + blocked_count,
            "amount": str(total_amount.quantize(Decimal("0.01"))),
            "readyAmount": str(ready_amount.quantize(Decimal("0.01"))),
            "employees": list(page_obj.object_list),
        },
        "meta": {
            "page": page_obj.number,
            "pageSize": bounded_size,
            "count": count,
            "totalPages": max(1, paginator.num_pages),
            "rangeStart": range_start,
            "rangeEnd": range_end,
            "filteredStatus": normalized_status,
        },
    }


def salary_payment_batch_rows_context(
    *, company, batch_id, membership=None, page=1, page_size=50, search: str = "", status: str = "All"
) -> dict[str, object]:
    batch = (
        SalaryPaymentBatch.objects.for_company(company)
        .select_related("run", "export_template")
        .get(pk=batch_id)
    )
    rows_qs = SalaryPaymentRow.objects.for_company(company).filter(batch=batch).order_by("employee_number", "id")
    query = (search or "").strip()
    if query:
        rows_qs = rows_qs.filter(
            Q(employee_number__icontains=query)
            | Q(employee_name__icontains=query)
            | Q(bank_name__icontains=query)
            | Q(bank_code__icontains=query)
            | Q(transaction_reference__icontains=query)
            | Q(failure_reason__icontains=query)
        )
    normalized_status = (status or "All").strip().lower().replace(" ", "_")
    if normalized_status not in {"", "all"}:
        valid = {value for value, _label in SalaryPaymentRowStatus.choices}
        if normalized_status in valid:
            rows_qs = rows_qs.filter(status=normalized_status)
    bounded_size = _bounded_page_size(page_size)
    paginator = Paginator(rows_qs, bounded_size)
    page_obj = paginator.get_page(_bounded_page(page))
    can_pay = bool(membership and membership_has_capability(membership, Capability.PAY))
    summary_qs = SalaryPaymentRow.objects.for_company(company).filter(batch=batch)
    summary = {
        "count": summary_qs.count(),
        "pendingCount": summary_qs.filter(status=SalaryPaymentRowStatus.PENDING).count(),
        "processingCount": summary_qs.filter(status=SalaryPaymentRowStatus.PROCESSING).count(),
        "paidCount": summary_qs.filter(status=SalaryPaymentRowStatus.PAID).count(),
        "failedCount": summary_qs.filter(status=SalaryPaymentRowStatus.FAILED).count(),
        "reversedCount": summary_qs.filter(status=SalaryPaymentRowStatus.REVERSED).count(),
        "cancelledCount": summary_qs.filter(status=SalaryPaymentRowStatus.CANCELLED).count(),
        "amount": str((summary_qs.aggregate(value=Sum("amount"))["value"] or Decimal("0")).quantize(Decimal("0.01"))),
        "paidAmount": str((summary_qs.filter(status=SalaryPaymentRowStatus.PAID).aggregate(value=Sum("amount"))["value"] or Decimal("0")).quantize(Decimal("0.01"))),
    }
    count = paginator.count
    return {
        "surface": "salary_payment_batch_rows_page",
        "period": f"{batch.run.period_start:%Y-%m}",
        "batch": serialize_payment_batch(batch, membership=membership, include_rows=False),
        "rows": [serialize_payment_row(row, can_pay=can_pay) for row in page_obj.object_list],
        "summary": summary,
        "meta": {
            "page": page_obj.number,
            "pageSize": bounded_size,
            "count": count,
            "totalPages": max(1, paginator.num_pages),
            "rangeStart": page_obj.start_index() if count else 0,
            "rangeEnd": page_obj.end_index() if count else 0,
        },
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
        "batches": [serialize_payment_batch(item, membership=membership) for item in batches],
        "bankReadinessTemplateId": str(active_bank_template.pk) if active_bank_template else None,
        "wpsReadinessTemplateId": str(active_wps_template.pk) if active_wps_template else None,
        "bankReadiness": _serialize_readiness(company=company, run=run, channel=BankExportChannel.BANK_CSV, template=active_bank_template),
        "wpsReadiness": _serialize_readiness(company=company, run=run, channel=BankExportChannel.WPS, template=active_wps_template),
        "canEditSetup": bool(membership and membership_can_edit(membership, Workspace.INTERNAL)),
        "canPay": bool(membership and membership_has_capability(membership, Capability.PAY)),
    }
