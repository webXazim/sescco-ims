from __future__ import annotations

import base64
import csv
import io
import os
from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import DocumentType
from apps.documents.services.documents import finalize_business_document
from apps.internal_payroll.models import (
    AttendancePeriod,
    AttendancePeriodStatus,
    BankExportChannel,
    BankExportDelimiter,
    BankExportEncoding,
    BankExportTemplate,
    CompanySalaryPaymentSettings,
    EmploymentStatus,
    EmployeePaymentProfile,
    InternalEmployee,
    InternalPayrollPolicy,
    OvertimePolicy,
    PaymentDestination,
    PayrollAdjustment,
    PayrollAdjustmentStatus,
    PayrollAdjustmentType,
    PayrollProrationMethod,
    PayrollRun,
    PayrollRunStatus,
    SalaryComponent,
    SalaryComponentCalculation,
    SalaryComponentCategory,
    SalaryComponentRecurrence,
    SalaryPaymentBatch,
    SalaryPaymentBatchStatus,
    SalaryPaymentRow,
    SalaryStructure,
    WPSMapping,
    iban_is_valid,
)
from apps.internal_payroll.services import (
    assign_employee_salary_structure,
    calculate_payroll_run,
    close_salary_payment_batch,
    create_bank_export_template,
    create_branch,
    create_department,
    create_employee,
    create_overtime_policy,
    create_payroll_adjustment,
    create_salary_component,
    export_salary_payment_batch,
    import_salary_payment_results,
    prepare_salary_payment_batch,
    save_attendance_entries,
    save_overtime_entries,
    start_salary_payment_batch,
    transition_attendance_period,
    transition_payroll_adjustment,
    transition_payroll_run,
    update_company_salary_payment_settings,
    update_payroll_policy,
    upsert_employee_payment_profile,
)
from apps.projects.models import Project
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalAdjustment,
    RentalAdjustmentStatus,
    RentalAdjustmentType,
    RentalRateType,
    RentalSettlementStatus,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    RentalWorker,
    RentalWorkerStatus,
    SupplierPayment,
    SupplierPaymentMethod,
    SupplierPaymentStatus,
    SupplierSettlement,
    SupplierStatus,
    WorkerAssignment,
)
from apps.rental_manpower.services import (
    assign_worker,
    calculate_project_settlements,
    create_project,
    create_rental_adjustment,
    create_supplier,
    create_worker,
    record_supplier_payment,
    save_timesheet_entries,
    save_timesheet_overtime,
    transition_project_settlements,
    transition_rental_adjustment,
    transition_timesheet,
)


D = Decimal

# 1x1 neutral PNG used only to exercise private branding upload/snapshot plumbing in TEST seed data.
DEMO_BRANDING_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlW9WQAAAAASUVORK5CYII=")

INTERNAL_EMPLOYEES = (
    ("DEMO-101", "Mehrab Wahid", "General Manager", "MGMT", D("15000")),
    ("DEMO-102", "Imran Hossain", "Business Development Manager", "SALES", D("6000")),
    ("DEMO-103", "Shaik Azzezullah", "Network Manager", "OPS", D("7000")),
    ("DEMO-104", "Md Salim Reza", "Construction Manager", "OPS", D("9000")),
    ("DEMO-105", "Md. Zahid Hossain", "Accountant", "FIN", D("6000")),
    ("DEMO-106", "Thohid Islam Amirul Islam", "Safety Supervisor", "OPS", D("4500")),
    ("DEMO-107", "Md Rockib Hosen", "Technician", "OPS", D("3000")),
    ("DEMO-108", "Alsagha Mahdi Jumah M", "Labor", "LAB", D("1800")),
    ("DEMO-109", "MD Abdullah Al Mamun", "Civil Engineer", "ENG", D("4000")),
    ("DEMO-110", "ALSAEGH AMAL ABDULHADI M", "Labor", "LAB", D("1800")),
    ("DEMO-111", "Shawon Khandokar", "Office Boy", "OPS", D("1200")),
    ("DEMO-112", "Md Haider Ali", "Steel Fixer", "LAB", D("1500")),
    ("DEMO-113", "Md Aminur Daradar", "Labor", "LAB", D("1250")),
    ("DEMO-114", "Md Ariful Islam", "Labor", "LAB", D("1200")),
    ("DEMO-115", "Aftab Uddin", "QC", "OPS", D("5000")),
    ("DEMO-116", "Salwa Yousef I Almuhaysin", "Sales", "SALES", D("5500")),
    ("DEMO-117", "Mainul Islam", "Civil Engineer", "ENG", D("4200")),
    ("DEMO-118", "Md Mokaremuzzaman", "Civil Engineer", "ENG", D("4200")),
)

DEPARTMENTS = {
    "MGMT": ("DEMO-MGMT", "Management"),
    "SALES": ("DEMO-SALES", "Sales"),
    "OPS": ("DEMO-OPS", "Operations"),
    "FIN": ("DEMO-FIN", "Finance"),
    "LAB": ("DEMO-LAB", "Site Labour"),
    "ENG": ("DEMO-ENG", "Engineering"),
}

RENTAL_WORKERS = (
    ("Hasan", "Cook", D("10.00")),
    ("Sajeed", "Driver", D("12.00")),
    ("MD Khabirl Islam Shohag", "Coordinator", D("15.00")),
    ("Mohasin", "Mason", D("14.00")),
    ("Rasel", "Mason", D("14.00")),
    ("Sobuj", "Mason", D("14.00")),
    ("Shifullah", "Mason", D("14.00")),
    ("Sumon", "Mason", D("14.00")),
    ("Ahad", "Mason", D("14.00")),
    ("Din Islam", "Mason", D("14.00")),
    ("Nawab Ali", "Mason", D("14.00")),
    ("Kifayet Ullah", "Mason", D("14.00")),
    ("Rafique Mia", "Mason", D("14.00")),
    ("Ekbal Surpat Ali", "Mason", D("14.00")),
    ("Ekbal Hosen", "Mason", D("14.00")),
    ("MD Saddam Kalim", "Helper/Mason", D("11.00")),
    ("Aslam", "Helper", D("9.00")),
    ("MD Alamin", "Helper", D("9.00")),
    ("Monir", "Helper", D("9.00")),
    ("Faruque", "Helper", D("9.00")),
    ("Joshim", "Helper", D("9.00")),
    ("Kashem", "Helper", D("9.00")),
    ("MD Faisal Sarder", "Helper", D("9.00")),
    ("MD Chan Mia", "Helper", D("9.00")),
    ("Rafid Rahoman", "Helper", D("9.00")),
    ("Akramul Haque", "Helper", D("9.00")),
    ("Sohel Rana", "Helper", D("9.00")),
    ("MD Mikael Hosen Mamun", "New Helper", D("9.00")),
    ("MD Antor Parvez", "New Helper", D("9.00")),
    ("MD Niloy", "New Helper", D("9.00")),
)

WPS_COLUMNS = [
    "bank_code",
    "iban",
    "net_salary",
    "transaction_reference",
    "employee_name",
    "national_id",
    "employee_address",
    "basic_salary",
    "housing_allowance",
    "other_earnings",
    "deductions",
]
WPS_HEADERS = [
    "Bank",
    "Account Number",
    "Total Salary",
    "Transaction Reference",
    "Employee Name",
    "National ID/Iqama ID",
    "Employee Address",
    "Basic Salary",
    "Housing Allowance",
    "Other Earnings",
    "Deductions",
]
WPS_RESULTS = {
    "employee": "Employee ID",
    "status": "Status",
    "reference": "Reference",
    "reason": "Reason",
}


def _month_start(raw: str) -> date:
    try:
        parsed = date.fromisoformat(f"{raw.strip()}-01")
    except (TypeError, ValueError) as exc:
        raise CommandError("--period must use YYYY-MM, for example 2026-09.") from exc
    return parsed


def _previous_month(value: date) -> date:
    return (value.replace(day=1) - timedelta(days=1)).replace(day=1)


def _month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def _days(value: date):
    day = value
    end = _month_end(value)
    while day <= end:
        yield day
        day += timedelta(days=1)


def _demo_iban(index: int) -> str:
    # Synthetic Saudi IBAN with a valid ISO-13616 checksum. Never derived from uploaded bank data.
    bban = f"99{index:018d}"[-20:]
    check = 98 - (int(f"{bban}281000") % 97)  # SA -> 28 10, then check digits 00.
    iban = f"SA{check:02d}{bban}"
    if not iban_is_valid(iban):  # defensive guard against accidental fixture corruption
        raise CommandError("Unable to generate a valid synthetic Saudi IBAN.")
    return iban


def _national_id(prefix: str, index: int) -> str:
    return f"{prefix}{index:06d}"


class Command(BaseCommand):
    help = (
        "Seed deterministic TEST payroll fixtures for Internal Company and Rental Manpower. "
        "All created identities/references are DEMO-prefixed and do not reuse uploaded bank or ID data."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default=os.getenv("IMS_SEED_COMPANY_SLUG", ""))
        parser.add_argument("--period", default=os.getenv("IMS_SEED_PERIOD", ""), help="Draft test period as YYYY-MM.")

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        membership = self._owner(company)
        period_start = self._period(company, options["period"])
        previous_start = _previous_month(period_start)
        clean_demo_company = self._demo_history_is_safe(company)

        self.stdout.write(self.style.WARNING("Seeding explicit TEST payroll data; DEMO/RDEMO records are not production payroll records."))
        try:
            with transaction.atomic():
                self._seed_company_document_identity(company)
                internal = self._seed_internal(company, membership, period_start, previous_start, clean_demo_company)
                rental = self._seed_rental(company, membership, period_start, previous_start, clean_demo_company)
        except ValidationError as exc:
            raise CommandError(f"Payroll test seed failed validation: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Payroll test seed complete for {company.slug}: "
            f"{internal['employees']} internal employees, {rental['workers']} rental workers, "
            f"draft period {period_start:%Y-%m}."
        ))
        if clean_demo_company:
            self.stdout.write(self.style.SUCCESS(f"Closed end-to-end history is available for {previous_start:%Y-%m}."))
        else:
            self.stdout.write(self.style.WARNING(
                "Closed-history generation was skipped because non-demo payroll masters exist. "
                "Draft DEMO fixtures were still seeded without touching real payroll history."
            ))

    def _company(self, slug: str) -> Company:
        qs = Company.objects.filter(
            is_active=True,
            memberships__is_active=True,
            memberships__role=AccessRole.OWNER,
            memberships__user__is_active=True,
        ).distinct()
        if slug:
            company = qs.filter(slug=slug.strip()).first()
            if not company:
                raise CommandError(f"No active company with an active owner matches slug '{slug}'.")
            return company
        rows = list(qs[:2])
        if len(rows) != 1:
            raise CommandError(
                "Choose the seed tenant explicitly with --company-slug or IMS_SEED_COMPANY_SLUG when more than one active company exists."
            )
        return rows[0]

    def _owner(self, company: Company) -> CompanyMembership:
        membership = (
            CompanyMembership.objects.select_related("company", "user")
            .filter(company=company, role=AccessRole.OWNER, is_active=True, user__is_active=True)
            .order_by("joined_at")
            .first()
        )
        if not membership:
            raise CommandError("The selected company needs an active owner membership before payroll test data can be seeded.")
        return membership

    def _period(self, company: Company, raw: str) -> date:
        if raw:
            return _month_start(raw)
        tz_name = getattr(getattr(company, "settings", None), "timezone", "Asia/Riyadh")
        return timezone.now().astimezone(ZoneInfo(tz_name)).date().replace(day=1)

    def _demo_history_is_safe(self, company: Company) -> bool:
        real_internal = InternalEmployee.objects.for_company(company).exclude(employee_number__startswith="DEMO-").exists()
        real_rental = RentalWorker.objects.for_company(company).exclude(worker_number__startswith="RDEMO-").exists()
        return not real_internal and not real_rental

    def _seed_company_document_identity(self, company):
        settings = company.settings
        changed = []
        if not settings.commercial_registration:
            settings.commercial_registration = "DEMO-CR-000001"; changed.append("commercial_registration")
        if not settings.vat_number:
            settings.vat_number = "DEMO-VAT-000001"; changed.append("vat_number")
        if not settings.document_address:
            settings.document_address = "TEST DATA · King Fahad Road, Dammam, Saudi Arabia"; changed.append("document_address")
        if not settings.document_email:
            settings.document_email = "payroll-demo@example.com"; changed.append("document_email")
        if not settings.document_phone:
            settings.document_phone = "+966500000000"; changed.append("document_phone")
        if not settings.website:
            settings.website = "https://example.com"; changed.append("website")
        for field_name, file_name in (("document_logo", "demo-logo.png"), ("document_letterhead", "demo-letterhead.png"), ("document_watermark", "demo-watermark.png")):
            field = getattr(settings, field_name)
            if not field:
                field.save(file_name, ContentFile(DEMO_BRANDING_PNG), save=False); changed.append(field_name)
        if changed:
            settings.save(update_fields=tuple(changed) + ("updated_at",))

    def _seed_internal(self, company, actor, current_start, previous_start, make_history):
        branch = company.internal_branches.filter(code="DEMO-HQ").first() if hasattr(company, "internal_branches") else None
        if branch is None:
            from apps.internal_payroll.models import Branch
            branch = Branch.objects.for_company(company).filter(code="DEMO-HQ").first()
        if branch is None:
            branch = create_branch(
                actor_membership=actor, code="DEMO-HQ", name="Demo Head Office", location="Dammam",
                address="TEST DATA · Dammam, Saudi Arabia", manager_name="Demo Payroll Manager",
            )

        from apps.internal_payroll.models import Department
        departments = {}
        for key, (code, name) in DEPARTMENTS.items():
            obj = Department.objects.for_company(company).filter(code=code).first()
            if obj is None:
                obj = create_department(actor_membership=actor, code=code, name=f"{name} (TEST)", notes="TEST DATA")
            departments[key] = obj

        joining = min(date(previous_start.year, 1, 1), previous_start)
        employees = []
        for index, (number, name, position, dep_key, basic) in enumerate(INTERNAL_EMPLOYEES, start=1):
            employee = InternalEmployee.objects.for_company(company).filter(employee_number=number).first()
            if employee is None:
                employee = create_employee(
                    actor_membership=actor,
                    employee_number=number,
                    full_name=name,
                    joining_date=joining,
                    branch_id=branch.pk,
                    department_id=departments[dep_key].pk,
                    position=position,
                    status=EmploymentStatus.ACTIVE,
                    national_id=_national_id("DEMO-IQAMA-", index),
                    phone=f"+96650000{index:04d}",
                    address=f"TEST DATA · Employee {index}, Dammam, Saudi Arabia",
                    reason="TEST DATA seed",
                )
            employees.append((employee, basic))

        components = self._internal_components(company, actor)
        overtime_policy = OvertimePolicy.objects.for_company(company).filter(code="DEMO-OT-300-15").first()
        if overtime_policy is None:
            overtime_policy = create_overtime_policy(
                actor_membership=actor,
                code="DEMO-OT-300-15",
                name="Basic / 300 × 1.5 (TEST)",
                base_component_id=components["basic"].pk,
                divisor=D("300"),
                multiplier=D("1.5"),
                notes="TEST DATA · mirrors the source payroll overtime formula.",
            )

        for employee, basic in employees:
            has_structure = SalaryStructure.objects.for_company(company).filter(
                employee=employee,
                effective_from__lte=joining,
            ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=joining)).exists()
            if not has_structure:
                professional = basic >= D("3000")
                assign_employee_salary_structure(
                    actor_membership=actor,
                    employee_id=employee.pk,
                    effective_from=joining,
                    components=[
                        {"component_id": components["basic"].pk, "amount": basic},
                        {"component_id": components["house"].pk, "amount": (basic * D("0.20")).quantize(D("0.01"))},
                        {"component_id": components["mobile"].pk, "amount": D("200") if professional else D("100")},
                        {"component_id": components["food"].pk, "amount": D("300")},
                        {"component_id": components["car"].pk, "amount": D("0")},
                    ],
                    overtime_policy_id=overtime_policy.pk,
                    notes="TEST DATA salary structure",
                )

        policy = InternalPayrollPolicy.objects.for_company(company).first()
        if policy is None or policy.proration_method == PayrollProrationMethod.NOT_CONFIGURED:
            update_payroll_policy(actor_membership=actor, proration_method=PayrollProrationMethod.NO_PRORATION)

        for index, (employee, _basic) in enumerate(employees, start=1):
            if not EmployeePaymentProfile.objects.for_company(company).filter(employee=employee).exists():
                upsert_employee_payment_profile(
                    actor_membership=actor,
                    employee_id=employee.pk,
                    values={
                        "destination_type": PaymentDestination.IBAN,
                        "account_holder_name": employee.full_name,
                        "bank_name": "Demo Payroll Bank",
                        "bank_code": "DEMO",
                        "iban": _demo_iban(1000 + index),
                        "wps_enabled": True,
                        "is_active": True,
                        "mark_verified": True,
                    },
                )

        payment_settings = CompanySalaryPaymentSettings.objects.for_company(company).first()
        missing_values = {}
        desired = {
            "employer_identifier": "DEMO-EMPLOYER",
            "employer_bank_name": "Demo Payroll Bank",
            "employer_bank_code": "DEMO",
            "employer_iban": _demo_iban(900001),
            "bank_customer_reference": "DEMO-CUSTOMER",
        }
        for key, value in desired.items():
            if payment_settings is None or not getattr(payment_settings, key):
                missing_values[key] = value
        if missing_values:
            update_company_salary_payment_settings(actor_membership=actor, values=missing_values)

        template = BankExportTemplate.objects.for_company(company).filter(code="DEMO-WPS-CSV").first()
        if template is None:
            template = create_bank_export_template(
                actor_membership=actor,
                code="DEMO-WPS-CSV",
                name="Source-compatible WPS CSV (TEST)",
                channel=BankExportChannel.WPS,
                delimiter=BankExportDelimiter.COMMA,
                encoding=BankExportEncoding.UTF8,
                include_header=True,
                columns=WPS_COLUMNS,
                headers=WPS_HEADERS,
                result_columns=WPS_RESULTS,
            )

        self._seed_internal_period(actor, employees, current_start, close=False, template=template)
        self._draft_internal_adjustments(company, actor, employees, current_start)
        if make_history:
            self._seed_internal_period(actor, employees, previous_start, close=True, template=template)
        return {"employees": len(employees)}

    def _internal_components(self, company, actor):
        basic = SalaryComponent.objects.for_company(company).filter(is_active=True, wps_mapping=WPSMapping.BASIC_SALARY).first()
        if basic is None:
            basic = create_salary_component(
                actor_membership=actor, code="DEMO-BASIC", name="Basic Salary (TEST)",
                category=SalaryComponentCategory.EARNING, recurrence=SalaryComponentRecurrence.RECURRING,
                calculation=SalaryComponentCalculation.FIXED_AMOUNT, wps_mapping=WPSMapping.BASIC_SALARY,
                notes="TEST DATA",
            )

        specs = {
            "house": ("DEMO-HOUSE", "Housing Allowance (TEST)", SalaryComponentCategory.EARNING, WPSMapping.HOUSING_ALLOWANCE),
            "mobile": ("DEMO-MOBILE", "Mobile Bill (TEST)", SalaryComponentCategory.EARNING, WPSMapping.OTHER_EARNINGS),
            "food": ("DEMO-FOOD", "Food Allowance (TEST)", SalaryComponentCategory.EARNING, WPSMapping.OTHER_EARNINGS),
            "car": ("DEMO-CAR", "Car Installment (TEST)", SalaryComponentCategory.DEDUCTION, WPSMapping.DEDUCTIONS),
        }
        result = {"basic": basic}
        for key, (code, name, category, mapping) in specs.items():
            obj = SalaryComponent.objects.for_company(company).filter(code=code).first()
            if obj is None:
                obj = create_salary_component(
                    actor_membership=actor, code=code, name=name, category=category,
                    recurrence=SalaryComponentRecurrence.RECURRING,
                    calculation=SalaryComponentCalculation.FIXED_AMOUNT,
                    wps_mapping=mapping, notes="TEST DATA",
                )
            result[key] = obj
        return result

    def _attendance_rows(self, employees, period_start):
        rows = []
        for emp_index, (employee, _basic) in enumerate(employees):
            weekdays = [d for d in _days(period_start) if d.weekday() not in {4, 5}]
            special = {}
            if weekdays and emp_index == 0:
                special[weekdays[min(2, len(weekdays) - 1)]] = "A"
            if weekdays and emp_index == 1:
                special[weekdays[min(5, len(weekdays) - 1)]] = "S"
            if weekdays and emp_index == 2:
                special[weekdays[min(8, len(weekdays) - 1)]] = "L"
            for work_date in _days(period_start):
                if work_date in special:
                    value = special[work_date]
                elif work_date.weekday() in {4, 5}:
                    value = "OFF"
                else:
                    value = "8"
                rows.append({"employee_id": employee.pk, "date": work_date, "value": value, "note": "TEST DATA"})
        return rows

    def _seed_internal_period(self, actor, employees, period_start, *, close, template):
        company = actor.company
        period = AttendancePeriod.objects.for_company(company).filter(period_start=period_start).first()
        if period is None or period.status == AttendancePeriodStatus.DRAFT:
            save_attendance_entries(actor_membership=actor, period_start=period_start, entries=self._attendance_rows(employees, period_start))
            ot_hours = {"DEMO-107": "12", "DEMO-109": "18", "DEMO-111": "6", "DEMO-112": "9", "DEMO-113": "8", "DEMO-114": "10", "DEMO-117": "16"}
            save_overtime_entries(
                actor_membership=actor,
                period_start=period_start,
                entries=[{"employee_id": employee.pk, "hours": ot_hours.get(employee.employee_number, "0")} for employee, _ in employees],
            )
        if not close:
            return

        self._approved_internal_adjustments(company, actor, employees, period_start)
        period = AttendancePeriod.objects.for_company(company).get(period_start=period_start)
        if period.status == AttendancePeriodStatus.DRAFT:
            transition_attendance_period(actor_membership=actor, period_start=period_start, action="submit")
            period.refresh_from_db()
        if period.status == AttendancePeriodStatus.SUBMITTED:
            transition_attendance_period(actor_membership=actor, period_start=period_start, action="approve")
            period.refresh_from_db()
        if period.status == AttendancePeriodStatus.APPROVED:
            transition_attendance_period(actor_membership=actor, period_start=period_start, action="lock")

        run = PayrollRun.objects.for_company(company).filter(period_start=period_start).first()
        if run is None or run.status == PayrollRunStatus.DRAFT:
            run = calculate_payroll_run(actor_membership=actor, period_start=period_start)
        if run.status == PayrollRunStatus.CALCULATED:
            run = transition_payroll_run(actor_membership=actor, period_start=period_start, action="submit_review")
        if run.status == PayrollRunStatus.REVIEW:
            run = transition_payroll_run(actor_membership=actor, period_start=period_start, action="approve", confirmed=True, note="TEST DATA approved history")

        batch = SalaryPaymentBatch.objects.for_company(company).filter(run=run, status__in=[
            SalaryPaymentBatchStatus.PREPARED, SalaryPaymentBatchStatus.EXPORTED, SalaryPaymentBatchStatus.PROCESSING,
            SalaryPaymentBatchStatus.PARTIALLY_PAID, SalaryPaymentBatchStatus.ATTENTION,
            SalaryPaymentBatchStatus.PAID, SalaryPaymentBatchStatus.CLOSED,
        ]).order_by("created_at").first()
        if batch is None and run.status == PayrollRunStatus.APPROVED:
            batch = prepare_salary_payment_batch(
                actor_membership=actor, period_start=period_start, channel=BankExportChannel.WPS,
                template_id=template.pk, note="TEST DATA closed WPS lifecycle",
            )
        if batch is not None and batch.status == SalaryPaymentBatchStatus.PREPARED:
            batch, _data, _name, _content_type = export_salary_payment_batch(actor_membership=actor, batch_id=batch.pk)
        if batch is not None and batch.status == SalaryPaymentBatchStatus.EXPORTED:
            batch = start_salary_payment_batch(actor_membership=actor, batch_id=batch.pk)
        if batch is not None and batch.status in {SalaryPaymentBatchStatus.PROCESSING, SalaryPaymentBatchStatus.PARTIALLY_PAID, SalaryPaymentBatchStatus.ATTENTION}:
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow([WPS_RESULTS["employee"], WPS_RESULTS["status"], WPS_RESULTS["reference"], WPS_RESULTS["reason"]])
            for row in SalaryPaymentRow.objects.for_company(company).filter(batch=batch).order_by("employee_number"):
                writer.writerow([row.employee_number, "Paid", f"DEMO-WPS-{period_start:%Y%m}-{row.employee_number}", ""])
            batch, _import_row, errors = import_salary_payment_results(
                actor_membership=actor, batch_id=batch.pk, file_name=f"DEMO-WPS-{period_start:%Y-%m}-result.csv", content=output.getvalue()
            )
            if errors:
                raise ValidationError({"seed": errors[:5]})
        if batch is not None and batch.status == SalaryPaymentBatchStatus.PAID:
            batch = close_salary_payment_batch(actor_membership=actor, batch_id=batch.pk)

        period = AttendancePeriod.objects.for_company(company).get(period_start=period_start)
        finalize_business_document(actor_membership=actor, document_type=DocumentType.INTERNAL_TIMESHEET, source_id=period.pk)
        run = PayrollRun.objects.for_company(company).get(period_start=period_start)
        for line in run.lines.all():
            finalize_business_document(actor_membership=actor, document_type=DocumentType.SALARY_SLIP, source_id=line.pk)
        if batch is not None:
            for row in batch.rows.filter(status="paid"):
                finalize_business_document(actor_membership=actor, document_type=DocumentType.SALARY_PAYMENT_RECEIPT, source_id=row.pk)

    def _draft_internal_adjustments(self, company, actor, employees, period_start):
        employee = employees[0][0]
        ref = f"DEMO-{period_start:%Y%m}-ADV"
        if not PayrollAdjustment.objects.for_company(company).filter(reference=ref).exists():
            create_payroll_adjustment(
                actor_membership=actor, employee_id=employee.pk, transaction_date=period_start,
                period_start=period_start, adjustment_type=PayrollAdjustmentType.SALARY_ADVANCE,
                amount=D("500"), reason="TEST DATA salary advance", reference=ref,
                recovery_plan="Recover next payroll", installment_amount=D("500"), recovery_start=_month_start(f"{(period_start + timedelta(days=32)).year:04d}-{(period_start + timedelta(days=32)).month:02d}"),
            )

    def _approved_internal_adjustments(self, company, actor, employees, period_start):
        fixtures = [
            (employees[1][0], PayrollAdjustmentType.BONUS, D("250"), "BONUS"),
            (employees[2][0], PayrollAdjustmentType.FINE, D("50"), "FINE"),
            (employees[3][0], PayrollAdjustmentType.REIMBURSEMENT, D("125"), "REIMB"),
        ]
        for employee, kind, amount, suffix in fixtures:
            ref = f"DEMO-{period_start:%Y%m}-{suffix}"
            adjustment = PayrollAdjustment.objects.for_company(company).filter(reference=ref).first()
            if adjustment is None:
                adjustment = create_payroll_adjustment(
                    actor_membership=actor, employee_id=employee.pk, transaction_date=period_start,
                    period_start=period_start, adjustment_type=kind, amount=amount,
                    reason=f"TEST DATA {kind}", reference=ref,
                )
            if adjustment.status == PayrollAdjustmentStatus.DRAFT:
                adjustment = transition_payroll_adjustment(actor_membership=actor, adjustment_id=adjustment.pk, action="submit")
            if adjustment.status == PayrollAdjustmentStatus.REVIEW:
                transition_payroll_adjustment(actor_membership=actor, adjustment_id=adjustment.pk, action="approve")

    def _seed_rental(self, company, actor, current_start, previous_start, make_history):
        supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-01").first()
        if supplier is None:
            supplier = create_supplier(
                actor_membership=actor, code="DEMO-SUP-01", name="Demo Manpower Supplier (TEST)",
                status=SupplierStatus.ACTIVE, contact_person="Demo Supplier Contact", phone="+966500009999",
                email="demo-supplier@example.invalid", payment_terms="30 days", address="TEST DATA · Saudi Arabia", notes="TEST DATA",
            )
        project = Project.objects.for_company(company).filter(code="DEMO-DIRIYA").first()
        if project is None:
            project = create_project(
                actor_membership=actor, code="DEMO-DIRIYA", name="Diriya (Six - Sense) Plaster Work (TEST)",
                start_date=previous_start, status=Project.Status.ACTIVE, client_name="Demo Client",
                location="Diriyah", manager_name="Demo Site Manager", notes="TEST DATA",
            )

        workers = []
        for index, (name, trade, rate) in enumerate(RENTAL_WORKERS, start=1):
            number = f"RDEMO-{index:03d}"
            worker = RentalWorker.objects.for_company(company).filter(worker_number=number).first()
            if worker is None:
                worker = create_worker(
                    actor_membership=actor, supplier_id=supplier.pk, worker_number=number, full_name=name,
                    national_id=_national_id("DEMO-R-IQAMA-", index), phone=f"+96651111{index:04d}",
                    status=RentalWorkerStatus.ACTIVE, notes="TEST DATA",
                )
            assignment = WorkerAssignment.objects.for_company(company).filter(
                worker=worker, project=project, cancelled_at__isnull=True,
                effective_from__lte=previous_start,
            ).filter(Q(effective_to__isnull=True) | Q(effective_to__gte=current_start)).first()
            if assignment is None:
                assign_worker(
                    actor_membership=actor, worker_id=worker.pk, project_id=project.reference,
                    trade=trade, rate_type=RentalRateType.HOURLY, rate=rate,
                    effective_date=previous_start, reason="TEST DATA project assignment",
                )
            workers.append(worker)

        self._seed_rental_period(company, actor, project, workers, current_start, close=False)
        self._draft_rental_adjustments(company, actor, project, workers, current_start)
        if make_history:
            self._seed_rental_period(company, actor, project, workers, previous_start, close=True)
        return {"workers": len(workers)}

    def _rental_rows(self, workers, period_start):
        rows = []
        for worker_index, worker in enumerate(workers):
            weekdays = [d for d in _days(period_start) if d.weekday() not in {4, 5}]
            special = {}
            if weekdays and worker_index == 0:
                special[weekdays[min(3, len(weekdays) - 1)]] = "A"
            if weekdays and worker_index == 1:
                special[weekdays[min(6, len(weekdays) - 1)]] = "N"
            if weekdays and worker_index == 2:
                special[weekdays[min(9, len(weekdays) - 1)]] = "L"
            for work_date in _days(period_start):
                if work_date in special:
                    value = special[work_date]
                elif work_date.weekday() in {4, 5}:
                    value = "OFF"
                else:
                    value = "10"
                rows.append({"worker_id": worker.pk, "work_date": work_date, "value": value, "note": "TEST DATA"})
        return rows

    def _seed_rental_period(self, company, actor, project, workers, period_start, *, close):
        period = RentalTimesheetPeriod.objects.for_company(company).filter(project=project, period_start=period_start).first()
        if period is None or period.status == RentalTimesheetStatus.DRAFT:
            save_timesheet_entries(actor_membership=actor, project_id=project.reference, period_start=period_start, entries=self._rental_rows(workers, period_start))
            # Mirrors the source rental sheet's 99 OT hours at SAR 6.75 without copying any bank/ID data.
            save_timesheet_overtime(
                actor_membership=actor, project_id=project.reference, period_start=period_start,
                worker_id=workers[1].pk, hours=D("99"), rate=D("6.75"),
            )
        if not close:
            return

        self._approved_rental_adjustment(company, actor, project, workers[3], period_start)
        period = RentalTimesheetPeriod.objects.for_company(company).get(project=project, period_start=period_start)
        if period.status == RentalTimesheetStatus.DRAFT:
            period = transition_timesheet(actor_membership=actor, project_id=project.reference, period_start=period_start, action="submit")
        if period.status == RentalTimesheetStatus.SUBMITTED:
            period = transition_timesheet(actor_membership=actor, project_id=project.reference, period_start=period_start, action="approve")
        if period.status == RentalTimesheetStatus.APPROVED:
            period = transition_timesheet(actor_membership=actor, project_id=project.reference, period_start=period_start, action="lock")

        settlements = list(SupplierSettlement.objects.for_company(company).filter(project=project, period_start=period_start))
        if not settlements:
            settlements = calculate_project_settlements(actor_membership=actor, project_id=project.reference, period_start=period_start)
        if settlements and all(row.status == RentalSettlementStatus.CALCULATED for row in settlements):
            settlements = transition_project_settlements(actor_membership=actor, project_id=project.reference, period_start=period_start, action="submit")
        if settlements and all(row.status == RentalSettlementStatus.REVIEW for row in settlements):
            settlements = transition_project_settlements(
                actor_membership=actor, project_id=project.reference, period_start=period_start,
                action="approve", confirmed=True, reason="TEST DATA approved history",
            )

        payments = []
        settlements = list(SupplierSettlement.objects.for_company(company).filter(project=project, period_start=period_start).order_by("supplier_code"))
        for settlement in settlements:
            payment = SupplierPayment.objects.for_company(company).filter(
                allocations__settlement=settlement, transaction_reference=f"DEMO-PAY-{period_start:%Y%m}-{settlement.supplier_code}"
            ).first()
            if payment is None and settlement.status in {
                RentalSettlementStatus.APPROVED, RentalSettlementStatus.PARTIALLY_PAID, RentalSettlementStatus.PAYMENT_PROCESSING
            }:
                payment = record_supplier_payment(
                    actor_membership=actor, settlement_id=settlement.pk, payment_date=_month_end(period_start),
                    method=SupplierPaymentMethod.BANK, amount=settlement.total_net, status=SupplierPaymentStatus.PAID,
                    transaction_reference=f"DEMO-PAY-{period_start:%Y%m}-{settlement.supplier_code}",
                    note="TEST DATA full supplier payment",
                )
            if payment:
                payments.append(payment)

        period = RentalTimesheetPeriod.objects.for_company(company).get(project=project, period_start=period_start)
        finalize_business_document(actor_membership=actor, document_type=DocumentType.RENTAL_TIMESHEET, source_id=period.pk)
        for settlement in SupplierSettlement.objects.for_company(company).filter(project=project, period_start=period_start):
            finalize_business_document(actor_membership=actor, document_type=DocumentType.SUPPLIER_SETTLEMENT, source_id=settlement.pk)
            finalize_business_document(
                actor_membership=actor, document_type=DocumentType.SUPPLIER_INVOICE, source_id=settlement.pk,
                invoice={
                    "invoice_number": f"DEMO-INV-{period_start:%Y%m}-{settlement.supplier_code}",
                    "issue_date": _month_end(period_start), "subtotal": settlement.total_net,
                    "vat_amount": D("0"), "total": settlement.total_net,
                },
            )
        for payment in payments:
            finalize_business_document(actor_membership=actor, document_type=DocumentType.SUPPLIER_PAYMENT_RECEIPT, source_id=payment.pk)

        settlements = list(SupplierSettlement.objects.for_company(company).filter(project=project, period_start=period_start))
        if settlements and all(row.status == RentalSettlementStatus.PAID for row in settlements):
            transition_project_settlements(actor_membership=actor, project_id=project.reference, period_start=period_start, action="close")

    def _draft_rental_adjustments(self, company, actor, project, workers, period_start):
        ref = f"DEMO-{period_start:%Y%m}-RENT-ADV"
        if not RentalAdjustment.objects.for_company(company).filter(reference=ref).exists():
            create_rental_adjustment(
                actor_membership=actor, worker_id=workers[0].pk, project_id=project.reference,
                transaction_date=period_start, period_start=period_start,
                adjustment_type=RentalAdjustmentType.ADVANCE, amount=D("180"),
                reason="TEST DATA worker advance", reference=ref,
            )

    def _approved_rental_adjustment(self, company, actor, project, worker, period_start):
        ref = f"DEMO-{period_start:%Y%m}-RENT-ADV"
        adjustment = RentalAdjustment.objects.for_company(company).filter(reference=ref).first()
        if adjustment is None:
            adjustment = create_rental_adjustment(
                actor_membership=actor, worker_id=worker.pk, project_id=project.reference,
                transaction_date=period_start, period_start=period_start,
                adjustment_type=RentalAdjustmentType.ADVANCE, amount=D("180"),
                reason="TEST DATA approved worker advance", reference=ref,
            )
        if adjustment.status == RentalAdjustmentStatus.DRAFT:
            adjustment = transition_rental_adjustment(actor_membership=actor, adjustment_id=adjustment.pk, action="submit")
        if adjustment.status == RentalAdjustmentStatus.REVIEW:
            transition_rental_adjustment(actor_membership=actor, adjustment_id=adjustment.pk, action="approve")
