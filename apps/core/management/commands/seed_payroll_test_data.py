from __future__ import annotations

import csv
import io
import os
import struct
import zlib
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
from apps.core.models import Company, DocumentBrandingMode
from apps.core.management import build_report
from apps.documents.models import BusinessDocument, DocumentType
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
    change_employee_lifecycle,
    archive_employee,
    delete_unused_employee,
    archive_branch,
    delete_unused_branch,
    restore_branch_trash,
    archive_department,
    delete_unused_department,
    restore_department_trash,
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
from apps.projects.services import archive_project, trash_unused_project
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
    transfer_worker,
    change_worker_rate,
    change_supplier_lifecycle,
    change_worker_lifecycle,
    archive_supplier,
    delete_unused_supplier,
    restore_supplier_trash,
    delete_unused_worker,
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


def _seed_supplier_payment_date(*, settlement, period_start: date) -> date:
    """Return a valid Paid date for a seeded supplier settlement.

    The closed DEMO period is intentionally historical, but the settlement workflow is
    executed when ``--seed`` runs. Production payment authority correctly rejects a
    payment dated before that approval. Keep the real authority intact and let the
    fixture date follow the later of period end and the actual approval date.
    """
    period_end = _month_end(period_start)
    approval_date = timezone.localdate(settlement.approved_at) if settlement.approved_at else timezone.localdate()
    payment_date = max(period_end, approval_date)
    if payment_date > timezone.localdate():
        raise ValidationError({
            "payment_date": "DEMO Paid supplier payment cannot use a future payment date."
        })
    return payment_date


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


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)


def _demo_brand_png(width: int, height: int, *, letterhead: bool = False, watermark: bool = False) -> bytes:
    """Generate a dependency-free DEMO PNG so --seed exercises branding storage/printing."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            if letterhead:
                top = y < max(5, height // 18)
                bottom = y >= height - max(5, height // 24)
                accent = x < max(6, width // 30) and y < max(18, height // 8)
                value = 32 if (top or bottom or accent) else 255
                alpha = 255
            elif watermark:
                cx, cy = width // 2, height // 2
                ring = abs(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - min(width, height) * 0.30) < 3
                value = 110 if ring or abs(x - y) < 2 or abs((width - x) - y) < 2 else 255
                alpha = 110 if value < 255 else 0
            else:
                value = 30 if x < width // 3 or y < height // 5 else 245
                alpha = 255
            rows.extend((value, value, value, alpha))
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return signature + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) + _png_chunk(b"IEND", b"")


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
        history_start = self._safe_history_period(company, period_start)
        clean_demo_company = self._demo_history_is_safe(company)

        self.stdout.write(self.style.WARNING("Seeding explicit TEST payroll data; DEMO/RDEMO records are not production payroll records."))
        try:
            with transaction.atomic():
                self._seed_document_branding(company, clean_demo_company)
                internal = self._seed_internal(company, membership, period_start, history_start, True)
                rental = self._seed_rental(company, membership, period_start, history_start, True)
                lifecycle = self._seed_lifecycle_scenarios(company, membership, period_start, history_start)
                reports = self._verify_report_coverage(company, period_start, history_start, True)
                documents = self._verify_document_coverage(company, history_start)
        except ValidationError as exc:
            raise CommandError(f"Payroll test seed failed validation: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(
            f"Payroll test seed complete for {company.slug}: "
            f"{internal['employees']} payroll employees, {rental['workers']} settlement workers, "
            f"{lifecycle['records']} lifecycle test records, draft period {period_start:%Y-%m}."
        ))
        if reports:
            self.stdout.write(self.style.SUCCESS(
                "Report/WPS test coverage verified: " + ", ".join(f"{name}={count}" for name, count in reports.items())
            ))
        if documents:
            self.stdout.write(self.style.SUCCESS(
                "Final document generation verified: " + ", ".join(f"{name}={count}" for name, count in documents.items())
            ))
        self.stdout.write(self.style.SUCCESS(
            f"Closed end-to-end DEMO history is available for {history_start:%Y-%m}; "
            "the seed chooses a collision-free period before non-DEMO employment begins."
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

    def _safe_history_period(self, company: Company, current_start: date) -> date:
        """Choose an idempotent closed DEMO period that cannot include real employees.

        A complete seed must exercise approval, WPS, documents and reports.  We therefore
        need one finalized payroll period even when the company already contains non-DEMO
        masters.  The chosen month must be after all existing DEMO employee joining dates,
        before the earliest non-DEMO employee joining date, and free from non-DEMO payroll/
        attendance history.  A previously seeded DEMO-only run is deliberately reused.
        """
        real_join = (
            InternalEmployee.objects.for_company(company)
            .exclude(employee_number__startswith="DEMO-")
            .exclude(joining_date__isnull=True)
            .order_by("joining_date")
            .values_list("joining_date", flat=True)
            .first()
        )
        demo_latest_join = (
            InternalEmployee.objects.for_company(company)
            .filter(employee_number__startswith="DEMO-")
            .order_by("-joining_date")
            .values_list("joining_date", flat=True)
            .first()
        )
        candidate = _previous_month(current_start)
        for _ in range(600):
            month_end = date(candidate.year, candidate.month, monthrange(candidate.year, candidate.month)[1])
            if real_join and month_end >= real_join:
                candidate = _previous_month(candidate)
                continue
            if demo_latest_join and candidate < demo_latest_join.replace(day=1):
                break

            run = PayrollRun.objects.for_company(company).filter(period_start=candidate).first()
            if run is not None:
                if not run.lines.exclude(employee_number__startswith="DEMO-").exists():
                    return candidate
                candidate = _previous_month(candidate)
                continue

            attendance = AttendancePeriod.objects.for_company(company).filter(period_start=candidate).first()
            if attendance is not None:
                if not attendance.entries.exclude(employee__employee_number__startswith="DEMO-").exists():
                    return candidate
                candidate = _previous_month(candidate)
                continue
            return candidate

        raise CommandError(
            "Unable to find a collision-free DEMO history month before existing non-DEMO employment. "
            "Choose a dedicated test tenant or remove conflicting test masters before using --seed."
        )

    def _demo_history_is_safe(self, company: Company) -> bool:
        real_internal = InternalEmployee.objects.for_company(company).exclude(employee_number__startswith="DEMO-").exists()
        real_rental = RentalWorker.objects.for_company(company).exclude(worker_number__startswith="RDEMO-").exists()
        return not real_internal and not real_rental

    def _seed_document_branding(self, company: Company, clean_demo_company: bool) -> None:
        if not clean_demo_company:
            return
        settings = company.settings
        update_fields = []
        identity_defaults = {
            "commercial_registration": "DEMO-CR-2050192960",
            "vat_number": "DEMO-VAT-312429950100003",
            "document_address": "TEST DATA · King Fahad Road, Dammam, Saudi Arabia",
            "document_email": "demo-payroll@example.invalid",
            "document_phone": "+966500000000",
            "website": "https://example.invalid",
        }
        for field_name, value in identity_defaults.items():
            if not getattr(settings, field_name):
                setattr(settings, field_name, value)
                update_fields.append(field_name)
        if not settings.document_logo:
            settings.document_logo.save("DEMO-logo.png", ContentFile(_demo_brand_png(160, 80), name="DEMO-logo.png"), save=False)
            update_fields.append("document_logo")
        if not settings.document_letterhead:
            settings.document_letterhead.save("DEMO-letterhead.png", ContentFile(_demo_brand_png(420, 594, letterhead=True), name="DEMO-letterhead.png"), save=False)
            update_fields.append("document_letterhead")
        if not settings.document_watermark:
            settings.document_watermark.save("DEMO-watermark.png", ContentFile(_demo_brand_png(220, 220, watermark=True), name="DEMO-watermark.png"), save=False)
            update_fields.append("document_watermark")
        if settings.document_branding_mode != DocumentBrandingMode.LETTERHEAD:
            settings.document_branding_mode = DocumentBrandingMode.LETTERHEAD
            update_fields.append("document_branding_mode")
        if update_fields:
            settings.save(update_fields=tuple(dict.fromkeys(update_fields + ["updated_at"])))

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

    def _seed_lifecycle_scenarios(self, company, actor, current_start, previous_start):
        """Seed deterministic lifecycle/operations fixtures that are intentionally outside payroll calculations."""
        from apps.internal_payroll.models import Branch, Department

        branch = Branch.objects.for_company(company).filter(code="DEMO-HQ").first()
        department = Department.objects.for_company(company).filter(code="DEMO-MGMT").first()
        if branch is None or department is None:
            raise ValidationError({"seed": "Internal DEMO organization masters must exist before lifecycle fixtures are created."})

        today = timezone.localdate()
        joining = min(previous_start, today - timedelta(days=90))
        employee_specs = (
            ("DEMO-190", "Demo Employee · On Leave", "leave"),
            ("DEMO-191", "Demo Employee · Inactive", "deactivate"),
            ("DEMO-192", "Demo Employee · Terminated", "terminate"),
            ("DEMO-193", "Demo Employee · Archived", "archive"),
            ("DEMO-194", "Demo Employee · Deleted", "delete"),
        )
        employee_records = 0
        for offset, (number, name, target) in enumerate(employee_specs, start=90):
            employee = InternalEmployee.objects.for_company(company).filter(employee_number=number).first()
            if employee is None:
                employee = create_employee(
                    actor_membership=actor,
                    employee_number=number,
                    full_name=name,
                    joining_date=joining,
                    branch_id=branch.pk,
                    department_id=department.pk,
                    position="Lifecycle Test Record",
                    status=EmploymentStatus.ACTIVE,
                    national_id=_national_id("DEMO-LIFE-IQAMA-", offset),
                    phone=f"+96652222{offset:04d}",
                    address="TEST DATA · Lifecycle scenario",
                    reason="TEST DATA lifecycle seed",
                )
            if employee.deleted_at:
                employee_records += 1
                continue
            if target == "leave" and employee.status == EmploymentStatus.ACTIVE and not employee.archived_at:
                change_employee_lifecycle(actor_membership=actor, employee_id=employee.pk, action="leave", reason="TEST DATA approved leave scenario")
            elif target == "deactivate" and employee.status == EmploymentStatus.ACTIVE and not employee.archived_at:
                change_employee_lifecycle(actor_membership=actor, employee_id=employee.pk, action="deactivate", reason="TEST DATA temporary stop scenario")
            elif target == "terminate" and employee.status != EmploymentStatus.TERMINATED and not employee.archived_at:
                stop_date = max(joining, min(today, current_start + timedelta(days=5)))
                change_employee_lifecycle(actor_membership=actor, employee_id=employee.pk, action="terminate", effective_date=stop_date, reason="TEST DATA employment termination scenario")
            elif target == "archive" and not employee.archived_at:
                archive_employee(actor_membership=actor, employee_id=employee.pk, reason="TEST DATA archive scenario")
            elif target == "delete":
                delete_unused_employee(actor_membership=actor, employee_id=employee.pk, confirmation=employee.employee_number, reason="TEST DATA 30-day recovery scenario")
            employee_records += 1

        # Empty organization masters exercise Archive/Delete independently without
        # contaminating the payroll employee register used by calculation fixtures.
        archived_branch = Branch.objects.for_company(company).filter(code="DEMO-BR-ARCH").first()
        if archived_branch is None:
            archived_branch = create_branch(
                actor_membership=actor, code="DEMO-BR-ARCH", name="Demo Archived Branch (TEST)",
                location="Dammam", address="TEST DATA", manager_name="Demo Manager",
            )
        if not archived_branch.archived_at and not archived_branch.deleted_at:
            archive_branch(actor_membership=actor, branch_id=archived_branch.pk, reason="TEST DATA branch archive fixture")

        deleted_branch = Branch.objects.for_company(company).filter(code="DEMO-BR-DEL").first()
        if deleted_branch is None:
            deleted_branch = create_branch(
                actor_membership=actor, code="DEMO-BR-DEL", name="Demo Deleted Branch (TEST)",
                location="Dammam", address="TEST DATA", manager_name="Demo Manager",
            )
        if deleted_branch.deleted_at:
            deleted_branch = restore_branch_trash(actor_membership=actor, branch_id=deleted_branch.pk)
        branch_child = InternalEmployee.objects.for_company(company).filter(employee_number="DEMO-196").first()
        if branch_child is None:
            branch_child = create_employee(
                actor_membership=actor, employee_number="DEMO-196", full_name="Demo Branch Cascade Child",
                joining_date=joining, branch_id=deleted_branch.pk, department_id=department.pk,
                position="Cascade Test Record", status=EmploymentStatus.ACTIVE,
                national_id=_national_id("DEMO-LIFE-IQAMA-", 196), phone="+966522220196",
                address="TEST DATA · Branch cascade child", reason="TEST DATA cascade seed",
            )
        if not deleted_branch.deleted_at:
            delete_unused_branch(
                actor_membership=actor, branch_id=deleted_branch.pk, confirmation=deleted_branch.code,
                reason="TEST DATA branch 30-day recovery cascade fixture",
            )
        # The lifecycle service refetches/locks the parent internally, so this
        # caller-held instance is intentionally stale after Delete. Refresh the
        # parent before comparing the shared cascade recovery window.
        deleted_branch.refresh_from_db()
        branch_child.refresh_from_db()
        if (
            not branch_child.deleted_at
            or branch_child.deleted_at != deleted_branch.deleted_at
            or branch_child.purge_after != deleted_branch.purge_after
        ):
            raise ValidationError({"seed": "Branch Trash cascade did not move its current employee into the same 30-day recovery window."})

        archived_department = Department.objects.for_company(company).filter(code="DEMO-DEP-ARCH").first()
        if archived_department is None:
            archived_department = create_department(
                actor_membership=actor, code="DEMO-DEP-ARCH", name="Demo Archived Department (TEST)",
                notes="TEST DATA lifecycle fixture",
            )
        if not archived_department.archived_at and not archived_department.deleted_at:
            archive_department(actor_membership=actor, department_id=archived_department.pk, reason="TEST DATA department archive fixture")

        deleted_department = Department.objects.for_company(company).filter(code="DEMO-DEP-DEL").first()
        if deleted_department is None:
            deleted_department = create_department(
                actor_membership=actor, code="DEMO-DEP-DEL", name="Demo Deleted Department (TEST)",
                notes="TEST DATA lifecycle fixture",
            )
        if deleted_department.deleted_at:
            deleted_department = restore_department_trash(actor_membership=actor, department_id=deleted_department.pk)
        department_child = InternalEmployee.objects.for_company(company).filter(employee_number="DEMO-197").first()
        if department_child is None:
            department_child = create_employee(
                actor_membership=actor, employee_number="DEMO-197", full_name="Demo Department Cascade Child",
                joining_date=joining, branch_id=branch.pk, department_id=deleted_department.pk,
                position="Cascade Test Record", status=EmploymentStatus.ACTIVE,
                national_id=_national_id("DEMO-LIFE-IQAMA-", 197), phone="+966522220197",
                address="TEST DATA · Department cascade child", reason="TEST DATA cascade seed",
            )
        if not deleted_department.deleted_at:
            delete_unused_department(
                actor_membership=actor, department_id=deleted_department.pk, confirmation=deleted_department.code,
                reason="TEST DATA department 30-day recovery cascade fixture",
            )
        deleted_department.refresh_from_db()
        department_child.refresh_from_db()
        if (
            not department_child.deleted_at
            or department_child.deleted_at != deleted_department.deleted_at
            or department_child.purge_after != deleted_department.purge_after
        ):
            raise ValidationError({"seed": "Department Trash cascade did not move its current employee into the same 30-day recovery window."})

        main_supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-01").first()
        main_project = Project.objects.for_company(company).filter(code="DEMO-DIRIYA").first()
        if main_supplier is None or main_project is None:
            raise ValidationError({"seed": "Rental DEMO supplier/project must exist before lifecycle fixtures are created."})

        secondary_project = Project.objects.for_company(company).filter(code="DEMO-YARD").first()
        if secondary_project is None:
            secondary_project = create_project(
                actor_membership=actor,
                code="DEMO-YARD",
                name="Demo Logistics Yard (TEST)",
                start_date=current_start,
                status=Project.Status.ACTIVE,
                client_name="Demo Internal Site",
                location="Dammam",
                manager_name="Demo Yard Manager",
                notes="TEST DATA · transfer/rate-change report fixture",
            )

        transfer_fixture_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-090").first()
        if transfer_fixture_worker is None:
            transfer_fixture_worker = create_worker(
                actor_membership=actor,
                supplier_id=main_supplier.pk,
                worker_number="RDEMO-090",
                full_name="Demo Transfer Worker",
                national_id=_national_id("DEMO-R-LIFE-", 90),
                phone="+966533330090",
                status=RentalWorkerStatus.ACTIVE,
                notes="TEST DATA · assignment transfer/rate report fixture",
            )
        transfer_day = current_start + timedelta(days=1)
        rate_day = transfer_day + timedelta(days=1)
        transfer_assignments = WorkerAssignment.objects.for_company(company).filter(worker=transfer_fixture_worker, cancelled_at__isnull=True)
        if not transfer_assignments.exists():
            assign_worker(
                actor_membership=actor,
                worker_id=transfer_fixture_worker.pk,
                project_id=main_project.reference,
                trade="Helper",
                rate_type=RentalRateType.HOURLY,
                rate=D("10"),
                effective_date=current_start,
                reason="TEST DATA initial assignment",
            )
        if not transfer_assignments.filter(project=secondary_project, effective_from=transfer_day).exists():
            transfer_worker(
                actor_membership=actor,
                worker_id=transfer_fixture_worker.pk,
                project_id=secondary_project.reference,
                trade="Helper",
                rate_type=RentalRateType.HOURLY,
                rate=D("10"),
                effective_date=transfer_day,
                reason="TEST DATA transfer report scenario",
            )
        if not WorkerAssignment.objects.for_company(company).filter(
            worker=transfer_fixture_worker,
            project=secondary_project,
            effective_from=rate_day,
            change_type="rate_change",
            cancelled_at__isnull=True,
        ).exists():
            change_worker_rate(
                actor_membership=actor,
                worker_id=transfer_fixture_worker.pk,
                rate_type=RentalRateType.HOURLY,
                rate=D("11"),
                effective_date=rate_day,
                reason="TEST DATA rate-change report scenario",
            )

        inactive_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-091").first()
        if inactive_worker is None:
            inactive_worker = create_worker(actor_membership=actor, supplier_id=main_supplier.pk, worker_number="RDEMO-091", full_name="Demo Inactive Worker", national_id=_national_id("DEMO-R-LIFE-", 91), phone="+966533330091", status=RentalWorkerStatus.ACTIVE, notes="TEST DATA · inactive worker lifecycle")
        if inactive_worker.status == RentalWorkerStatus.ACTIVE:
            change_worker_lifecycle(actor_membership=actor, worker_id=inactive_worker.pk, action="deactivate", effective_date=min(today, current_start + timedelta(days=3)), reason="TEST DATA temporary worker stop")

        terminated_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-092").first()
        if terminated_worker is None:
            terminated_worker = create_worker(actor_membership=actor, supplier_id=main_supplier.pk, worker_number="RDEMO-092", full_name="Demo Terminated Worker", national_id=_national_id("DEMO-R-LIFE-", 92), phone="+966533330092", status=RentalWorkerStatus.ACTIVE, notes="TEST DATA · terminated worker lifecycle")
        if terminated_worker.status != RentalWorkerStatus.TERMINATED:
            if not WorkerAssignment.objects.for_company(company).filter(worker=terminated_worker, cancelled_at__isnull=True, effective_to__isnull=True).exists():
                assign_worker(actor_membership=actor, worker_id=terminated_worker.pk, project_id=secondary_project.reference, trade="Driver", rate_type=RentalRateType.HOURLY, rate=D("12"), effective_date=current_start, reason="TEST DATA worker termination assignment")
            change_worker_lifecycle(actor_membership=actor, worker_id=terminated_worker.pk, action="terminate", effective_date=min(today, current_start + timedelta(days=4)), reason="TEST DATA worker contract ended")

        inactive_supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-INACTIVE").first()
        if inactive_supplier is None:
            inactive_supplier = create_supplier(actor_membership=actor, code="DEMO-SUP-INACTIVE", name="Demo Inactive Supplier (TEST)", status=SupplierStatus.ACTIVE, contact_person="Demo Contact", phone="+966544440001", email="inactive-supplier@example.invalid", payment_terms="30 days", address="TEST DATA", notes="TEST DATA · temporary supplier stop")
        if inactive_supplier.status == SupplierStatus.ACTIVE:
            change_supplier_lifecycle(actor_membership=actor, supplier_id=inactive_supplier.pk, action="deactivate", reason="TEST DATA temporary supplier stop")

        terminated_supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-TERM").first()
        if terminated_supplier is None:
            terminated_supplier = create_supplier(actor_membership=actor, code="DEMO-SUP-TERM", name="Demo Terminated Supplier (TEST)", status=SupplierStatus.ACTIVE, contact_person="Demo Terminated Contact", phone="+966544440002", email="terminated-supplier@example.invalid", payment_terms="30 days", address="TEST DATA", notes="TEST DATA · supplier termination cascade")
        supplier_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-093").first()
        if supplier_worker is None:
            supplier_worker = create_worker(actor_membership=actor, supplier_id=terminated_supplier.pk, worker_number="RDEMO-093", full_name="Demo Supplier-Terminated Worker", national_id=_national_id("DEMO-R-LIFE-", 93), phone="+966533330093", status=RentalWorkerStatus.ACTIVE, notes="TEST DATA · supplier cascade termination")
        if terminated_supplier.status != SupplierStatus.TERMINATED:
            if not WorkerAssignment.objects.for_company(company).filter(worker=supplier_worker, cancelled_at__isnull=True, effective_to__isnull=True).exists():
                assign_worker(actor_membership=actor, worker_id=supplier_worker.pk, project_id=secondary_project.reference, trade="Mason", rate_type=RentalRateType.HOURLY, rate=D("14"), effective_date=current_start, reason="TEST DATA supplier termination assignment")
            change_supplier_lifecycle(actor_membership=actor, supplier_id=terminated_supplier.pk, action="terminate", effective_date=min(today, current_start + timedelta(days=6)), reason="TEST DATA supplier relationship terminated")

        archived_supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-ARCH").first()
        if archived_supplier is None:
            archived_supplier = create_supplier(
                actor_membership=actor, code="DEMO-SUP-ARCH", name="Demo Archived Supplier (TEST)",
                status=SupplierStatus.ACTIVE, contact_person="Demo Contact", phone="+966544440003",
                email="archived-supplier@example.invalid", address="TEST DATA", notes="TEST DATA archive fixture",
            )
        if not archived_supplier.archived_at and not archived_supplier.deleted_at:
            archive_supplier(actor_membership=actor, supplier_id=archived_supplier.pk, reason="TEST DATA supplier archive fixture")

        deleted_supplier = ManpowerSupplier.objects.for_company(company).filter(code="DEMO-SUP-DEL").first()
        if deleted_supplier is None:
            deleted_supplier = create_supplier(
                actor_membership=actor, code="DEMO-SUP-DEL", name="Demo Deleted Supplier (TEST)",
                status=SupplierStatus.ACTIVE, contact_person="Demo Contact", phone="+966544440004",
                email="deleted-supplier@example.invalid", address="TEST DATA", notes="TEST DATA delete fixture",
            )
        if deleted_supplier.deleted_at:
            deleted_supplier = restore_supplier_trash(actor_membership=actor, supplier_id=deleted_supplier.pk)
        supplier_cascade_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-096").first()
        if supplier_cascade_worker is None:
            supplier_cascade_worker = create_worker(
                actor_membership=actor, supplier_id=deleted_supplier.pk, worker_number="RDEMO-096",
                full_name="Demo Supplier Cascade Worker", national_id=_national_id("DEMO-R-LIFE-", 96),
                phone="+966533330096", status=RentalWorkerStatus.ACTIVE,
                notes="TEST DATA · supplier delete cascade child",
            )
        if not deleted_supplier.deleted_at:
            delete_unused_supplier(
                actor_membership=actor, supplier_id=deleted_supplier.pk, confirmation=deleted_supplier.code,
                reason="TEST DATA supplier 30-day recovery cascade fixture",
            )
        deleted_supplier.refresh_from_db()
        supplier_cascade_worker.refresh_from_db()
        if (
            not supplier_cascade_worker.deleted_at
            or supplier_cascade_worker.deleted_at != deleted_supplier.deleted_at
            or supplier_cascade_worker.purge_after != deleted_supplier.purge_after
        ):
            raise ValidationError({"seed": "Supplier Trash cascade did not move its workers into the same 30-day recovery window."})

        project_specs = (
            ("DEMO-HOLD", "Demo Project On Hold (TEST)", Project.Status.ON_HOLD, None),
            ("DEMO-DONE", "Demo Completed Project (TEST)", Project.Status.COMPLETED, min(today, current_start)),
            ("DEMO-ARCH", "Demo Archived Project (TEST)", Project.Status.ACTIVE, None),
            ("DEMO-DEL", "Demo Deleted Project (TEST)", Project.Status.ACTIVE, None),
        )
        lifecycle_projects = {}
        for code, name, status, end_date in project_specs:
            project = Project.objects.for_company(company).filter(code=code).first()
            if project is None:
                start_date = min(previous_start, end_date or current_start)
                project = create_project(
                    actor_membership=actor, code=code, name=name, start_date=start_date, end_date=end_date,
                    status=status, client_name="Demo Client", location="Dammam", manager_name="Demo Manager",
                    notes="TEST DATA project lifecycle fixture",
                )
            lifecycle_projects[code] = project
        project = lifecycle_projects["DEMO-ARCH"]
        if not project.archived_at and not project.deleted_at:
            archive_project(actor_membership=actor, project_id=project.reference, reason="TEST DATA project archive fixture")
        project = lifecycle_projects["DEMO-DEL"]
        if not project.deleted_at:
            trash_unused_project(
                actor_membership=actor, project_id=project.reference, confirmation=project.code,
                reason="TEST DATA project 30-day recovery fixture",
            )

        archived_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-094").first()
        if archived_worker is None:
            archived_worker = create_worker(actor_membership=actor, supplier_id=main_supplier.pk, worker_number="RDEMO-094", full_name="Demo Archived Worker", national_id=_national_id("DEMO-R-LIFE-", 94), phone="+966533330094", status=RentalWorkerStatus.ACTIVE, notes="TEST DATA · archive page fixture")
        if not archived_worker.archived_at:
            change_worker_lifecycle(actor_membership=actor, worker_id=archived_worker.pk, action="archive", reason="TEST DATA archive page fixture")

        deleted_worker = RentalWorker.objects.for_company(company).filter(worker_number="RDEMO-095").first()
        if deleted_worker is None:
            deleted_worker = create_worker(actor_membership=actor, supplier_id=main_supplier.pk, worker_number="RDEMO-095", full_name="Demo Deleted Worker", national_id=_national_id("DEMO-R-LIFE-", 95), phone="+966533330095", status=RentalWorkerStatus.ACTIVE, notes="TEST DATA · delete recovery page fixture")
        if not deleted_worker.deleted_at:
            delete_unused_worker(actor_membership=actor, worker_id=deleted_worker.pk, confirmation=deleted_worker.worker_number, reason="TEST DATA 30-day worker recovery fixture")

        return {"records": employee_records + 22}

    def _verify_report_coverage(self, company, current_start, previous_start, complete_history):
        """Fail the seed if a supposedly complete DEMO tenant cannot exercise report generation."""
        cases = []
        if complete_history:
            cases.extend([
                ("workforce-cost", "management", previous_start),
                ("internal-payroll", "internal", previous_start),
                ("internal-overtime", "internal", previous_start, "overtime"),
                ("internal-adjustments", "internal", previous_start, "advances"),
                ("internal-payments", "internal", previous_start, "payments"),
                ("rental-project-cost", "rental", previous_start),
                ("supplier-cost", "rental", previous_start),
                ("rental-overtime", "rental", previous_start, "overtime"),
                ("rental-adjustments", "rental", previous_start, "advances"),
                ("rental-payments", "rental", previous_start, "payments"),
            ])
        cases.extend([
            ("wps", "internal", current_start),
            ("transfers", "rental", current_start),
        ])
        coverage = {}
        for item in cases:
            name, workspace, period = item[:3]
            report_type = item[3] if len(item) > 3 else name
            report = build_report(company=company, report_type=report_type, period_start=period, workspace=workspace)
            rows = list(report.get("rows") or [])
            coverage[name] = len(rows)
            if not rows:
                raise ValidationError({"seed": f"DEMO report coverage is empty for {name} ({workspace}, {period:%Y-%m})."})
        return coverage

    def _verify_document_coverage(self, company, period_start):
        """Require every payroll printable document type in the closed DEMO period."""
        coverage = {}
        for document_type, _label in DocumentType.choices:
            count = BusinessDocument.objects.for_company(company).filter(
                document_type=document_type, period_start=period_start
            ).count()
            coverage[document_type] = count
            if not count:
                raise ValidationError({
                    "seed": f"DEMO final document coverage is empty for {document_type} ({period_start:%Y-%m})."
                })
        return coverage


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
                    actor_membership=actor, settlement_id=settlement.pk,
                    payment_date=_seed_supplier_payment_date(settlement=settlement, period_start=period_start),
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
