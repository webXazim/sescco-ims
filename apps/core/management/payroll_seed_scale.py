from __future__ import annotations

import hashlib
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Iterator, TypeVar

from django.core.exceptions import ValidationError
from django.db.models import Count
from django.utils import timezone

from apps.core.encryption import sensitive_fingerprint
from apps.internal_payroll.models import (
    AttendanceCode,
    AttendanceEntry,
    AttendanceOvertimeEntry,
    AttendancePeriod,
    AttendancePeriodStatus,
    BankExportChannel,
    BankExportTemplate,
    Branch,
    BranchKind,
    CompanySalaryPaymentSettings,
    Department,
    EmployeeOrganizationAssignment,
    EmployeePaymentProfile,
    EmploymentStatus,
    InternalEmployee,
    OvertimePolicy,
    PaymentDestination,
    PayrollAdjustment,
    PayrollAdjustmentStatus,
    PayrollAdjustmentType,
    PayrollRun,
    PayrollRunLine,
    PayrollRunStatus,
    SalaryComponent,
    SalaryPaymentBatch,
    SalaryPaymentBatchStatus,
    SalaryPaymentRow,
    SalaryPaymentRowStatus,
    SalaryStructure,
    SalaryStructureLine,
    WPSMapping,
)
from apps.projects.models import Project
from apps.rental_manpower.models import (
    AssignmentChangeType,
    ManpowerSupplier,
    ReleaseDisposition,
    RentalAdjustment,
    RentalAdjustmentStatus,
    RentalAdjustmentType,
    RentalAttendanceCode,
    RentalRateType,
    RentalSettlementStatus,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    RentalWorker,
    RentalWorkerStatus,
    SupplierPayment,
    SupplierPaymentAllocation,
    SupplierPaymentMethod,
    SupplierPaymentStatus,
    SupplierSettlement,
    SupplierSettlementLine,
    SupplierStatus,
    WorkerAssignment,
)

D = Decimal
T = TypeVar("T")

INTERNAL_PREFIX = "DEMO-SCALE-I-"
RENTAL_PREFIX = "RDEMO-SCALE-"
BRANCH_PREFIX = "DEMO-SCALE-BR-"
DEPARTMENT_PREFIX = "DEMO-SCALE-DEP-"
SUPPLIER_PREFIX = "DEMO-SCALE-SUP-"
PROJECT_PREFIX = "DEMO-SCALE-P-"
SOURCE_MARKER = "DEMO SCALE SEED"
FINGERPRINT_PREFIX = "demo-scale:"


@dataclass(frozen=True)
class PayrollScaleProfile:
    name: str
    internal_employees: int
    rental_workers: int
    branches: int
    departments: int
    suppliers: int
    projects: int
    months: int


SCALE_PROFILES: dict[str, PayrollScaleProfile] = {
    "realistic": PayrollScaleProfile(
        name="realistic",
        internal_employees=250,
        rental_workers=750,
        branches=6,
        departments=12,
        suppliers=8,
        projects=12,
        months=6,
    ),
    "benchmark": PayrollScaleProfile(
        name="benchmark",
        internal_employees=2000,
        rental_workers=5000,
        branches=15,
        departments=24,
        suppliers=30,
        projects=40,
        months=12,
    ),
}

MAX_PROFILE_MONTHS = max(profile.months for profile in SCALE_PROFILES.values())

INTERNAL_POSITIONS = (
    "Project Engineer",
    "Site Engineer",
    "Accountant",
    "Safety Officer",
    "QA/QC Inspector",
    "Supervisor",
    "Technician",
    "Coordinator",
    "Storekeeper",
    "Administrator",
)
RENTAL_TRADES = (
    "Mason",
    "Helper",
    "Carpenter",
    "Steel Fixer",
    "Electrician",
    "Plumber",
    "Driver",
    "Rigger",
    "Scaffolder",
    "Welder",
)


def get_scale_profile(name: str) -> PayrollScaleProfile:
    key = str(name or "").strip().lower()
    try:
        return SCALE_PROFILES[key]
    except KeyError as exc:
        raise ValidationError({"profile": f"Unknown payroll seed profile: {name!r}."}) from exc


def _month_shift(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 + months
    return date(total // 12, total % 12 + 1, 1)


def scale_months(anchor_period: date, count: int) -> tuple[date, ...]:
    """Return oldest->newest scale months immediately before the functional history month."""
    if anchor_period.day != 1:
        raise ValueError("anchor_period must be the first day of a month")
    return tuple(_month_shift(anchor_period, offset) for offset in range(-count, 0))


def _month_end(value: date) -> date:
    return value.replace(day=monthrange(value.year, value.month)[1])


def _days(value: date) -> Iterator[date]:
    current = value
    end = _month_end(value)
    while current <= end:
        yield current
        current += timedelta(days=1)


def _money(value: Decimal) -> Decimal:
    return value.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: Decimal) -> Decimal:
    return value.quantize(D("0.0001"), rounding=ROUND_HALF_UP)


def _synthetic_saudi_iban(index: int) -> str:
    # Same ISO-13616 construction as the functional seed, with a separate numeric range.
    bban = f"88{index:018d}"[-20:]
    check = 98 - (int(f"{bban}281000") % 97)
    return f"SA{check:02d}{bban}"


def _stable_sha256(*parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bulk_create(model, rows: Iterable[T], *, batch_size: int = 5000) -> int:
    chunk: list[T] = []
    attempted = 0
    for row in rows:
        chunk.append(row)
        if len(chunk) >= batch_size:
            model.objects.bulk_create(chunk, batch_size=batch_size, ignore_conflicts=True)
            attempted += len(chunk)
            chunk = []
    if chunk:
        model.objects.bulk_create(chunk, batch_size=batch_size, ignore_conflicts=True)
        attempted += len(chunk)
    return attempted


def _numeric_suffix(value: str) -> int:
    return int(value.rsplit("-", 1)[-1])


def _internal_salary(index: int) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    basic = D("1800") + D(index % 15) * D("350")
    housing = _money(basic * D("0.20"))
    mobile = D("200") if basic >= D("3000") else D("100")
    food = D("300")
    return _money(basic), housing, mobile, food


def _internal_state(index: int, anchor_period: date, now) -> dict[str, object]:
    end_date = anchor_period - timedelta(days=1)
    archived = index % 211 == 0
    if index % 97 == 0:
        return {
            "status": EmploymentStatus.TERMINATED,
            "employment_end_date": end_date,
            "archived_at": None,
            "archived_reason": "",
        }
    if archived:
        return {
            "status": EmploymentStatus.INACTIVE,
            "employment_end_date": None,
            "archived_at": now,
            "archived_reason": f"{SOURCE_MARKER} archived sample",
        }
    if index % 53 == 0:
        return {
            "status": EmploymentStatus.INACTIVE,
            "employment_end_date": None,
            "archived_at": None,
            "archived_reason": "",
        }
    if index % 41 == 0:
        return {
            "status": EmploymentStatus.ON_LEAVE,
            "employment_end_date": None,
            "archived_at": None,
            "archived_reason": "",
        }
    return {
        "status": EmploymentStatus.ACTIVE,
        "employment_end_date": None,
        "archived_at": None,
        "archived_reason": "",
    }


def _rental_state(index: int, anchor_period: date, now) -> dict[str, object]:
    inactive_date = anchor_period - timedelta(days=1)
    archived = index % 223 == 0
    if index % 101 == 0:
        return {
            "status": RentalWorkerStatus.TERMINATED,
            "inactive_on": None,
            "inactive_reason": "",
            "terminated_on": inactive_date,
            "termination_reason": f"{SOURCE_MARKER} termination sample",
            "archived_at": None,
            "archived_reason": "",
        }
    if archived:
        return {
            "status": RentalWorkerStatus.INACTIVE,
            "inactive_on": inactive_date,
            "inactive_reason": f"{SOURCE_MARKER} archived sample",
            "terminated_on": None,
            "termination_reason": "",
            "archived_at": now,
            "archived_reason": f"{SOURCE_MARKER} archived sample",
        }
    if index % 59 == 0:
        return {
            "status": RentalWorkerStatus.INACTIVE,
            "inactive_on": inactive_date,
            "inactive_reason": f"{SOURCE_MARKER} temporary stop sample",
            "terminated_on": None,
            "termination_reason": "",
            "archived_at": None,
            "archived_reason": "",
        }
    return {
        "status": RentalWorkerStatus.ACTIVE,
        "inactive_on": None,
        "inactive_reason": "",
        "terminated_on": None,
        "termination_reason": "",
        "archived_at": None,
        "archived_reason": "",
    }


def _internal_day_value(employee_index: int, work_date: date) -> tuple[Decimal, str]:
    if work_date.weekday() in {4, 5}:
        return D("0"), AttendanceCode.OFF
    ordinal = sum(1 for day in range(1, work_date.day + 1) if date(work_date.year, work_date.month, day).weekday() not in {4, 5})
    if employee_index % 37 == 0 and ordinal == 2:
        return D("0"), AttendanceCode.ABSENT
    if employee_index % 43 == 0 and ordinal == 4:
        return D("0"), AttendanceCode.LEAVE
    if employee_index % 47 == 0 and ordinal == 6:
        return D("0"), AttendanceCode.SICK
    if employee_index % 61 == 0 and ordinal == 8:
        return D("0"), AttendanceCode.HOLIDAY
    return D("8"), ""


def _internal_month_metrics(employee_index: int, period_start: date, basic: Decimal) -> dict[str, Decimal | int]:
    regular_hours = D("0")
    absent = leave = sick = holiday = off = 0
    for work_date in _days(period_start):
        hours, code = _internal_day_value(employee_index, work_date)
        regular_hours += hours
        absent += int(code == AttendanceCode.ABSENT)
        leave += int(code == AttendanceCode.LEAVE)
        sick += int(code == AttendanceCode.SICK)
        holiday += int(code == AttendanceCode.HOLIDAY)
        off += int(code == AttendanceCode.OFF)
    overtime_hours = D(str(8 + (employee_index % 3) * 2)) if employee_index % 5 == 0 else D("0")
    overtime_rate = _rate(basic / D("300") * D("1.5")) if overtime_hours else D("0")
    overtime_amount = _money(overtime_rate * overtime_hours)
    return {
        "regular_hours": regular_hours,
        "absent_days": absent,
        "leave_days": leave,
        "sick_days": sick,
        "holiday_days": holiday,
        "off_days": off,
        "overtime_hours": overtime_hours,
        "overtime_rate": overtime_rate,
        "overtime_amount": overtime_amount,
    }


def _rental_day_value(worker_index: int, work_date: date) -> tuple[Decimal, str]:
    if work_date.weekday() in {4, 5}:
        return D("0"), RentalAttendanceCode.OFF
    ordinal = sum(1 for day in range(1, work_date.day + 1) if date(work_date.year, work_date.month, day).weekday() not in {4, 5})
    if worker_index % 29 == 0 and ordinal == 2:
        return D("0"), RentalAttendanceCode.ABSENT
    if worker_index % 31 == 0 and ordinal == 4:
        return D("0"), RentalAttendanceCode.NO_SCOPE
    if worker_index % 37 == 0 and ordinal == 6:
        return D("0"), RentalAttendanceCode.LEAVE
    return D("10"), ""


def _rental_month_metrics(worker_index: int, period_start: date, assignment: WorkerAssignment) -> dict[str, Decimal | int]:
    regular_hours = D("0")
    work_days = 0
    for work_date in _days(period_start):
        hours, code = _rental_day_value(worker_index, work_date)
        regular_hours += hours
        if not code and hours > 0:
            work_days += 1
    overtime_hours = D(str(6 + (worker_index % 4))) if worker_index % 4 == 0 else D("0")
    overtime_rate = _rate(assignment.rate * D("1.5")) if overtime_hours else D("0")
    base_amount = _money(regular_hours * assignment.rate)
    overtime_amount = _money(overtime_hours * overtime_rate)
    adjustment_earnings = D("125") if worker_index % 17 == 0 else D("0")
    adjustment_deductions = D("80") if worker_index % 19 == 0 else D("0")
    gross = _money(base_amount + overtime_amount)
    net = _money(gross + adjustment_earnings - adjustment_deductions)
    return {
        "regular_hours": regular_hours,
        "work_days": work_days,
        "overtime_hours": overtime_hours,
        "overtime_rate": overtime_rate,
        "base_amount": base_amount,
        "overtime_amount": overtime_amount,
        "adjustment_earnings": adjustment_earnings,
        "adjustment_deductions": adjustment_deductions,
        "gross_amount": gross,
        "net_amount": net,
    }


class PayrollScaleSeeder:
    """Restart-safe large synthetic Payroll dataset builder.

    The functional DEMO seed remains the authority for workflow correctness. This builder adds
    high-cardinality, server-readable history for pagination/query/report/benchmark testing.
    Stable prefixes and unique references make every phase safe to rerun after interruption.
    """

    def __init__(self, *, company, actor, anchor_period: date, requested: PayrollScaleProfile, batch_size: int = 5000):
        self.company = company
        self.actor = actor
        self.user = actor.user
        self.anchor_period = anchor_period
        self.now = timezone.now()
        self.batch_size = max(500, int(batch_size))
        self.requested = requested
        self.profile = self._effective_profile(requested)
        self.months = scale_months(anchor_period, self.profile.months)
        # Keep employee/assignment eligibility stable when moving realistic -> benchmark later.
        self.origin = _month_shift(anchor_period, -max(MAX_PROFILE_MONTHS, self.profile.months))
        self.transfer_date = _month_shift(anchor_period, -3)
        self.final_scale_date = anchor_period - timedelta(days=1)

    def _effective_profile(self, requested: PayrollScaleProfile) -> PayrollScaleProfile:
        existing_months = PayrollRun.objects.for_company(self.company).filter(
            source_fingerprint__startswith=FINGERPRINT_PREFIX
        ).values("period_start").distinct().count()
        return PayrollScaleProfile(
            name=requested.name,
            internal_employees=max(
                requested.internal_employees,
                InternalEmployee.objects.for_company(self.company).filter(employee_number__startswith=INTERNAL_PREFIX).count(),
            ),
            rental_workers=max(
                requested.rental_workers,
                RentalWorker.objects.for_company(self.company).filter(worker_number__startswith=RENTAL_PREFIX).count(),
            ),
            branches=max(
                requested.branches,
                Branch.objects.for_company(self.company).filter(code__startswith=BRANCH_PREFIX).count(),
            ),
            departments=max(
                requested.departments,
                Department.objects.for_company(self.company).filter(code__startswith=DEPARTMENT_PREFIX).count(),
            ),
            suppliers=max(
                requested.suppliers,
                ManpowerSupplier.objects.for_company(self.company).filter(code__startswith=SUPPLIER_PREFIX).count(),
            ),
            projects=max(
                requested.projects,
                Project.objects.for_company(self.company).filter(code__startswith=PROJECT_PREFIX).count(),
            ),
            months=max(requested.months, existing_months),
        )

    def run(self) -> dict[str, int | str]:
        branches = self._ensure_branches()
        departments = self._ensure_departments()
        internal = self._ensure_internal_employees(branches, departments)
        salary_structures = self._ensure_salary_structures(internal)
        self._ensure_payment_profiles(internal)
        attendance_periods = self._ensure_internal_attendance(internal, salary_structures)
        payroll_runs = self._ensure_internal_financial_history(internal, attendance_periods)

        suppliers = self._ensure_suppliers()
        projects = self._ensure_projects()
        workers = self._ensure_rental_workers(suppliers, projects)
        assignments = self._rental_assignment_map(workers)
        timesheet_periods = self._ensure_rental_timesheets(workers, assignments, projects)
        settlements = self._ensure_rental_financial_history(workers, assignments, timesheet_periods)

        return self._verify(
            internal=internal,
            workers=workers,
            payroll_runs=payroll_runs,
            settlements=settlements,
        )

    def _ensure_branches(self) -> list[Branch]:
        codes = [f"{BRANCH_PREFIX}{index:03d}" for index in range(1, self.profile.branches + 1)]
        existing = set(Branch.objects.for_company(self.company).filter(code__in=codes).values_list("code", flat=True))
        rows = (
            Branch(
                company=self.company,
                code=code,
                name=f"Scale Test Office {index:03d}",
                location=("Dammam", "Khobar", "Riyadh", "Jubail")[index % 4],
                address=f"TEST DATA · Scale office {index:03d}, Saudi Arabia",
                manager_name=f"Scale Manager {index:03d}",
                kind=BranchKind.OFFICE if index % 3 == 0 else BranchKind.BRANCH,
                is_active=True,
            )
            for index, code in enumerate(codes, start=1)
            if code not in existing
        )
        _bulk_create(Branch, rows, batch_size=self.batch_size)
        return list(Branch.objects.for_company(self.company).filter(code__in=codes).order_by("code"))

    def _ensure_departments(self) -> list[Department]:
        codes = [f"{DEPARTMENT_PREFIX}{index:03d}" for index in range(1, self.profile.departments + 1)]
        existing = set(Department.objects.for_company(self.company).filter(code__in=codes).values_list("code", flat=True))
        rows = (
            Department(
                company=self.company,
                code=code,
                name=f"Scale Test Department {index:03d}",
                notes=f"{SOURCE_MARKER} · synthetic department",
                is_active=True,
            )
            for index, code in enumerate(codes, start=1)
            if code not in existing
        )
        _bulk_create(Department, rows, batch_size=self.batch_size)
        return list(Department.objects.for_company(self.company).filter(code__in=codes).order_by("code"))

    def _ensure_internal_employees(self, branches: list[Branch], departments: list[Department]) -> list[InternalEmployee]:
        numbers = [f"{INTERNAL_PREFIX}{index:05d}" for index in range(1, self.profile.internal_employees + 1)]
        existing_numbers = set(
            InternalEmployee.objects.for_company(self.company).filter(employee_number__in=numbers).values_list("employee_number", flat=True)
        )

        def employee_rows():
            for index, number in enumerate(numbers, start=1):
                if number in existing_numbers:
                    continue
                state = _internal_state(index, self.anchor_period, self.now)
                yield InternalEmployee(
                    company=self.company,
                    employee_number=number,
                    full_name=f"Scale Internal Employee {index:05d}",
                    national_id=f"DEMO-SCALE-IQ-{index:08d}",
                    phone=f"+96655{index:07d}",
                    address=f"TEST DATA · Scale employee {index:05d}, Saudi Arabia",
                    joining_date=self.origin,
                    status=state["status"],
                    employment_end_date=state["employment_end_date"],
                    archived_at=state["archived_at"],
                    archived_reason=state["archived_reason"],
                )

        _bulk_create(InternalEmployee, employee_rows(), batch_size=self.batch_size)
        employees = list(
            InternalEmployee.objects.for_company(self.company).filter(employee_number__in=numbers).order_by("employee_number")
        )
        self._ensure_internal_assignments(employees, branches, departments)
        return employees

    def _ensure_internal_assignments(
        self,
        employees: list[InternalEmployee],
        branches: list[Branch],
        departments: list[Department],
    ) -> None:
        employee_ids = [employee.pk for employee in employees]
        existing = set(
            EmployeeOrganizationAssignment.objects.for_company(self.company)
            .filter(employee_id__in=employee_ids, reason__startswith=SOURCE_MARKER)
            .values_list("employee_id", "effective_from")
        )

        def assignment_rows():
            for employee in employees:
                index = _numeric_suffix(employee.employee_number)
                branch = branches[(index - 1) % len(branches)]
                department = departments[(index - 1) % len(departments)]
                position = INTERNAL_POSITIONS[(index - 1) % len(INTERNAL_POSITIONS)]
                state = _internal_state(index, self.anchor_period, self.now)
                final_end = self.final_scale_date if state["status"] in {EmploymentStatus.INACTIVE, EmploymentStatus.TERMINATED} else None
                transfer = index % 10 == 0 and len(branches) > 1 and len(departments) > 1
                if transfer:
                    first_key = (employee.pk, self.origin)
                    if first_key not in existing:
                        yield EmployeeOrganizationAssignment(
                            company=self.company,
                            employee=employee,
                            branch=branch,
                            department=department,
                            position=position,
                            effective_from=self.origin,
                            effective_to=self.transfer_date - timedelta(days=1),
                            reason=f"{SOURCE_MARKER} initial assignment",
                        )
                    second_key = (employee.pk, self.transfer_date)
                    if second_key not in existing:
                        yield EmployeeOrganizationAssignment(
                            company=self.company,
                            employee=employee,
                            branch=branches[index % len(branches)],
                            department=departments[index % len(departments)],
                            position=position,
                            effective_from=self.transfer_date,
                            effective_to=final_end,
                            reason=f"{SOURCE_MARKER} transfer history",
                        )
                else:
                    key = (employee.pk, self.origin)
                    if key not in existing:
                        yield EmployeeOrganizationAssignment(
                            company=self.company,
                            employee=employee,
                            branch=branch,
                            department=department,
                            position=position,
                            effective_from=self.origin,
                            effective_to=final_end,
                            reason=f"{SOURCE_MARKER} organization assignment",
                        )

        _bulk_create(EmployeeOrganizationAssignment, assignment_rows(), batch_size=self.batch_size)

    def _ensure_salary_structures(self, employees: list[InternalEmployee]) -> dict[object, SalaryStructure]:
        components = {
            row.wps_mapping: row
            for row in SalaryComponent.objects.for_company(self.company).filter(
                code__in=["DEMO-BASIC", "DEMO-HOUSE", "DEMO-MOBILE", "DEMO-FOOD"]
            )
        }
        by_code = {
            row.code: row
            for row in SalaryComponent.objects.for_company(self.company).filter(
                code__in=["DEMO-BASIC", "DEMO-HOUSE", "DEMO-MOBILE", "DEMO-FOOD"]
            )
        }
        basic_component = components.get(WPSMapping.BASIC_SALARY) or by_code.get("DEMO-BASIC")
        overtime_policy = OvertimePolicy.objects.for_company(self.company).filter(code="DEMO-OT-300-15").first()
        required_codes = {"DEMO-BASIC", "DEMO-HOUSE", "DEMO-MOBILE", "DEMO-FOOD"}
        if not basic_component or not overtime_policy or not required_codes.issubset(by_code):
            raise ValidationError({"profile": "Run the functional payroll seed before a scale profile; salary masters are missing."})

        employee_ids = [employee.pk for employee in employees]
        existing_employee_ids = set(
            SalaryStructure.objects.for_company(self.company).filter(employee_id__in=employee_ids, effective_to__isnull=True).values_list("employee_id", flat=True)
        )
        rows = (
            SalaryStructure(
                company=self.company,
                employee=employee,
                effective_from=self.origin,
                overtime_policy=overtime_policy,
                overtime_policy_code=overtime_policy.code,
                overtime_policy_name=overtime_policy.name,
                overtime_base_component_code=basic_component.code,
                overtime_base_component_name=basic_component.name,
                overtime_divisor=D("300"),
                overtime_multiplier=D("1.5"),
                notes=f"{SOURCE_MARKER} salary structure",
            )
            for employee in employees
            if employee.pk not in existing_employee_ids
        )
        _bulk_create(SalaryStructure, rows, batch_size=self.batch_size)
        structures = {
            row.employee_id: row
            for row in SalaryStructure.objects.for_company(self.company)
            .filter(employee_id__in=employee_ids, effective_to__isnull=True)
            .select_related("employee")
        }
        component_rows = list(by_code.values())
        existing_lines = set(
            SalaryStructureLine.objects.for_company(self.company)
            .filter(structure_id__in=[row.pk for row in structures.values()], component_id__in=[row.pk for row in component_rows])
            .values_list("structure_id", "component_id")
        )

        def line_rows():
            for employee in employees:
                structure = structures[employee.pk]
                index = _numeric_suffix(employee.employee_number)
                basic, housing, mobile, food = _internal_salary(index)
                amounts = {
                    "DEMO-BASIC": basic,
                    "DEMO-HOUSE": housing,
                    "DEMO-MOBILE": mobile,
                    "DEMO-FOOD": food,
                }
                for code in ("DEMO-BASIC", "DEMO-HOUSE", "DEMO-MOBILE", "DEMO-FOOD"):
                    component = by_code[code]
                    if (structure.pk, component.pk) in existing_lines:
                        continue
                    yield SalaryStructureLine(
                        company=self.company,
                        structure=structure,
                        component=component,
                        amount=amounts[code],
                        component_code=component.code,
                        component_name=component.name,
                        component_category=component.category,
                        component_recurrence=component.recurrence,
                        component_calculation=component.calculation,
                        wps_mapping=component.wps_mapping,
                    )

        _bulk_create(SalaryStructureLine, line_rows(), batch_size=self.batch_size)
        return structures

    def _ensure_payment_profiles(self, employees: list[InternalEmployee]) -> None:
        employee_ids = [employee.pk for employee in employees]
        existing = set(
            EmployeePaymentProfile.objects.for_company(self.company).filter(employee_id__in=employee_ids).values_list("employee_id", flat=True)
        )

        def rows():
            for employee in employees:
                if employee.pk in existing:
                    continue
                index = _numeric_suffix(employee.employee_number)
                iban = _synthetic_saudi_iban(200000 + index)
                active = employee.status in {EmploymentStatus.ACTIVE, EmploymentStatus.ON_LEAVE} and not employee.archived_at
                yield EmployeePaymentProfile(
                    company=self.company,
                    employee=employee,
                    destination_type=PaymentDestination.IBAN,
                    account_holder_name=employee.full_name,
                    bank_name="Scale Test Payroll Bank",
                    bank_code="SCALE",
                    iban=iban,
                    iban_fingerprint=sensitive_fingerprint(iban),
                    salary_card_number="",
                    salary_card_fingerprint="",
                    wps_enabled=True,
                    is_active=active,
                    verified_at=self.now,
                    verified_by=self.user,
                )

        _bulk_create(EmployeePaymentProfile, rows(), batch_size=self.batch_size)

    def _ensure_internal_attendance(
        self,
        employees: list[InternalEmployee],
        salary_structures: dict[object, SalaryStructure],
    ) -> dict[date, AttendancePeriod]:
        existing_periods = set(
            AttendancePeriod.objects.for_company(self.company).filter(period_start__in=self.months).values_list("period_start", flat=True)
        )
        rows = (
            AttendancePeriod(
                company=self.company,
                period_start=period_start,
                period_end=_month_end(period_start),
                status=AttendancePeriodStatus.LOCKED,
                revision=1,
                submitted_at=self.now,
                submitted_by=self.user,
                approved_at=self.now,
                approved_by=self.user,
                locked_at=self.now,
                locked_by=self.user,
            )
            for period_start in self.months
            if period_start not in existing_periods
        )
        _bulk_create(AttendancePeriod, rows, batch_size=self.batch_size)
        periods = {
            row.period_start: row
            for row in AttendancePeriod.objects.for_company(self.company).filter(period_start__in=self.months)
        }
        employee_ids = [employee.pk for employee in employees]
        existing_pairs = set(
            AttendanceEntry.objects.for_company(self.company)
            .filter(period_id__in=[period.pk for period in periods.values()], employee_id__in=employee_ids)
            .values_list("period_id", "employee_id")
            .distinct()
        )

        def entry_rows():
            for period_start, period in periods.items():
                for employee in employees:
                    if (period.pk, employee.pk) in existing_pairs:
                        continue
                    index = _numeric_suffix(employee.employee_number)
                    for work_date in _days(period_start):
                        hours, code = _internal_day_value(index, work_date)
                        yield AttendanceEntry(
                            company=self.company,
                            period=period,
                            employee=employee,
                            work_date=work_date,
                            regular_hours=hours,
                            code=code,
                            note=SOURCE_MARKER,
                        )

        _bulk_create(AttendanceEntry, entry_rows(), batch_size=self.batch_size)

        overtime_pairs = set(
            AttendanceOvertimeEntry.objects.for_company(self.company)
            .filter(period_id__in=[period.pk for period in periods.values()], employee_id__in=employee_ids)
            .values_list("period_id", "employee_id")
        )

        def overtime_rows():
            for period_start, period in periods.items():
                for employee in employees:
                    index = _numeric_suffix(employee.employee_number)
                    if index % 5 != 0 or (period.pk, employee.pk) in overtime_pairs:
                        continue
                    basic, _housing, _mobile, _food = _internal_salary(index)
                    metrics = _internal_month_metrics(index, period_start, basic)
                    yield AttendanceOvertimeEntry(
                        company=self.company,
                        period=period,
                        employee=employee,
                        salary_structure=salary_structures[employee.pk],
                        hours=metrics["overtime_hours"],
                        policy_code="DEMO-OT-300-15",
                        policy_name="Basic / 300 × 1.5 (TEST)",
                        base_component_code="DEMO-BASIC",
                        base_component_name="Basic Salary (TEST)",
                        base_amount=basic,
                        divisor=D("300"),
                        multiplier=D("1.5"),
                        overtime_rate=metrics["overtime_rate"],
                        amount=metrics["overtime_amount"],
                    )

        _bulk_create(AttendanceOvertimeEntry, overtime_rows(), batch_size=self.batch_size)
        self._ensure_internal_adjustments(employees)
        return periods

    def _ensure_internal_adjustments(self, employees: list[InternalEmployee]) -> None:
        expected_refs: list[str] = []
        specs: list[tuple[InternalEmployee, date, str, Decimal, str]] = []
        for period_start in self.months:
            for employee in employees:
                index = _numeric_suffix(employee.employee_number)
                if index % 43 == 0:
                    expected_refs.append(f"DEMO-SCALE-ADJ-{period_start:%Y%m}-{index:05d}-ADV")
                    specs.append((employee, period_start, PayrollAdjustmentType.SALARY_ADVANCE, D("500"), expected_refs[-1]))
                if index % 17 == 0:
                    expected_refs.append(f"DEMO-SCALE-ADJ-{period_start:%Y%m}-{index:05d}-BON")
                    specs.append((employee, period_start, PayrollAdjustmentType.BONUS, D("150"), expected_refs[-1]))
                if index % 19 == 0:
                    expected_refs.append(f"DEMO-SCALE-ADJ-{period_start:%Y%m}-{index:05d}-FINE")
                    specs.append((employee, period_start, PayrollAdjustmentType.FINE, D("75"), expected_refs[-1]))
        existing = set(
            PayrollAdjustment.objects.for_company(self.company).filter(reference__in=expected_refs).values_list("reference", flat=True)
        )

        def rows():
            for employee, period_start, adjustment_type, amount, reference in specs:
                if reference in existing:
                    continue
                advance = adjustment_type == PayrollAdjustmentType.SALARY_ADVANCE
                yield PayrollAdjustment(
                    company=self.company,
                    employee=employee,
                    transaction_date=period_start + timedelta(days=14),
                    period_start=period_start,
                    adjustment_type=adjustment_type,
                    amount=amount,
                    reason=f"{SOURCE_MARKER} {adjustment_type}",
                    reference=reference,
                    recovery_plan="Five monthly installments" if advance else "",
                    installment_amount=D("100") if advance else None,
                    recovery_start=_month_shift(period_start, 1) if advance else None,
                    status=PayrollAdjustmentStatus.APPROVED,
                    submitted_at=self.now,
                    submitted_by=self.user,
                    approved_at=self.now,
                    approved_by=self.user,
                )

        _bulk_create(PayrollAdjustment, rows(), batch_size=self.batch_size)

    def _organization_assignment_map(self, employees: list[InternalEmployee]) -> dict[object, list[EmployeeOrganizationAssignment]]:
        result: dict[object, list[EmployeeOrganizationAssignment]] = {employee.pk: [] for employee in employees}
        rows = (
            EmployeeOrganizationAssignment.objects.for_company(self.company)
            .filter(employee_id__in=result)
            .select_related("branch", "department")
            .order_by("employee_id", "effective_from")
        )
        for row in rows:
            result[row.employee_id].append(row)
        return result

    @staticmethod
    def _organization_for_period(rows: list[EmployeeOrganizationAssignment], period_start: date) -> EmployeeOrganizationAssignment:
        period_end = _month_end(period_start)
        candidates = [
            row for row in rows
            if row.effective_from <= period_end and (row.effective_to is None or row.effective_to >= period_start)
        ]
        if not candidates:
            raise ValidationError({"profile": f"Scale employee has no organization assignment for {period_start:%Y-%m}."})
        return max(candidates, key=lambda row: row.effective_from)

    def _ensure_internal_financial_history(
        self,
        employees: list[InternalEmployee],
        attendance_periods: dict[date, AttendancePeriod],
    ) -> dict[date, PayrollRun]:
        organization = self._organization_assignment_map(employees)
        template = BankExportTemplate.objects.for_company(self.company).filter(code="DEMO-WPS-CSV").first()
        payment_settings = CompanySalaryPaymentSettings.objects.for_company(self.company).first()
        if template is None or payment_settings is None:
            raise ValidationError({"profile": "Functional WPS masters are missing before scale seeding."})

        runs: dict[date, PayrollRun] = {}
        for period_start in self.months:
            attendance = attendance_periods[period_start]
            run = PayrollRun.objects.for_company(self.company).filter(period_start=period_start).first()
            if run is None:
                run = PayrollRun.objects.create(
                    company=self.company,
                    period_start=period_start,
                    period_end=_month_end(period_start),
                    attendance_period=attendance,
                    attendance_revision=attendance.revision,
                    status=PayrollRunStatus.CLOSED,
                    revision=1,
                    calculation_version=1,
                    source_fingerprint=f"{FINGERPRINT_PREFIX}{period_start:%Y%m}",
                    snapshot_fingerprint=_stable_sha256("internal", period_start, self.profile.internal_employees),
                    calculated_at=self.now,
                    calculated_by=self.user,
                    submitted_at=self.now,
                    submitted_by=self.user,
                    approved_at=self.now,
                    approved_by=self.user,
                    reviewer_note=f"{SOURCE_MARKER} approved synthetic benchmark history",
                )
            runs[period_start] = run
            existing_employee_ids = set(run.lines.filter(employee_id__in=[employee.pk for employee in employees]).values_list("employee_id", flat=True))

            def line_rows():
                for employee in employees:
                    if employee.pk in existing_employee_ids:
                        continue
                    index = _numeric_suffix(employee.employee_number)
                    basic, housing, mobile, food = _internal_salary(index)
                    metrics = _internal_month_metrics(index, period_start, basic)
                    org = self._organization_for_period(organization[employee.pk], period_start)
                    allowances = _money(housing + mobile + food)
                    other_earnings = D("150") if index % 17 == 0 else D("0")
                    other_deductions = D("75") if index % 19 == 0 else D("0")
                    gross = _money(basic + allowances + metrics["overtime_amount"] + other_earnings)
                    deductions = _money(other_deductions)
                    net = _money(gross - deductions)
                    yield PayrollRunLine(
                        company=self.company,
                        run=run,
                        employee=employee,
                        employee_number=employee.employee_number,
                        employee_name=employee.full_name,
                        branch_id_snapshot=org.branch_id,
                        branch_code=org.branch.code,
                        branch_name=org.branch.name,
                        department_id_snapshot=org.department_id,
                        department_code=org.department.code,
                        department_name=org.department.name,
                        position=org.position,
                        regular_hours=metrics["regular_hours"],
                        absent_days=metrics["absent_days"],
                        leave_days=metrics["leave_days"],
                        sick_days=metrics["sick_days"],
                        holiday_days=metrics["holiday_days"],
                        off_days=metrics["off_days"],
                        overtime_hours=metrics["overtime_hours"],
                        overtime_amount=metrics["overtime_amount"],
                        overtime_policy_code="DEMO-OT-300-15" if metrics["overtime_hours"] else "",
                        overtime_policy_name="Basic / 300 × 1.5 (TEST)" if metrics["overtime_hours"] else "",
                        overtime_rate=metrics["overtime_rate"] if metrics["overtime_hours"] else None,
                        basic=basic,
                        allowances=allowances,
                        other_earnings=other_earnings,
                        gross=gross,
                        advance_recovery=D("0"),
                        other_deductions=other_deductions,
                        total_deductions=deductions,
                        net=net,
                    )

            _bulk_create(PayrollRunLine, line_rows(), batch_size=self.batch_size)
            lines = list(run.lines.filter(employee_id__in=[employee.pk for employee in employees]).select_related("employee"))
            totals = {
                "total_basic": sum((row.basic for row in lines), D("0")),
                "total_allowances": sum((row.allowances for row in lines), D("0")),
                "total_overtime": sum((row.overtime_amount for row in lines), D("0")),
                "total_other_earnings": sum((row.other_earnings for row in lines), D("0")),
                "total_gross": sum((row.gross for row in lines), D("0")),
                "total_advance_recovery": sum((row.advance_recovery for row in lines), D("0")),
                "total_other_deductions": sum((row.other_deductions for row in lines), D("0")),
                "total_deductions": sum((row.total_deductions for row in lines), D("0")),
                "total_net": sum((row.net for row in lines), D("0")),
            }
            PayrollRun.objects.filter(pk=run.pk).update(
                employee_count=len(lines),
                snapshot_fingerprint=_stable_sha256("internal", period_start, len(lines), totals["total_net"]),
                **{key: _money(value) for key, value in totals.items()},
            )
            run.refresh_from_db()
            self._ensure_salary_payment_batch(run, lines, template, payment_settings)
        return runs

    def _ensure_salary_payment_batch(self, run, lines, template, payment_settings) -> None:
        reference = f"DEMO-SCALE-WPS-{run.period_start:%Y%m}"
        total = _money(sum((line.net for line in lines), D("0")))
        batch = SalaryPaymentBatch.objects.for_company(self.company).filter(reference=reference).first()
        if batch is None:
            batch = SalaryPaymentBatch.objects.create(
                company=self.company,
                run=run,
                reference=reference,
                channel=BankExportChannel.WPS,
                export_template=template,
                template_code=template.code,
                template_name=template.name,
                delimiter=template.delimiter,
                encoding=template.encoding,
                include_header=template.include_header,
                columns=template.columns,
                headers=template.headers,
                result_columns=template.result_columns,
                status=SalaryPaymentBatchStatus.CLOSED,
                employee_count=len(lines),
                total_amount=total,
                paid_amount=total,
                source_fingerprint=_stable_sha256("wps", run.period_start, len(lines), total),
                last_export_sha256=_stable_sha256("wps-export", run.period_start),
                employer_identifier=payment_settings.employer_identifier,
                employer_bank_name=payment_settings.employer_bank_name,
                employer_bank_code=payment_settings.employer_bank_code,
                employer_iban=payment_settings.employer_iban,
                bank_customer_reference=payment_settings.bank_customer_reference,
                prepared_at=self.now,
                prepared_by=self.user,
                exported_at=self.now,
                exported_by=self.user,
                processing_at=self.now,
                processing_by=self.user,
                completed_at=self.now,
                closed_at=self.now,
                closed_by=self.user,
                note=f"{SOURCE_MARKER} closed WPS batch",
            )
        existing_line_ids = set(batch.rows.filter(run_line_id__in=[line.pk for line in lines]).values_list("run_line_id", flat=True))

        def rows():
            for line in lines:
                if line.pk in existing_line_ids:
                    continue
                index = _numeric_suffix(line.employee_number)
                iban = _synthetic_saudi_iban(200000 + index)
                yield SalaryPaymentRow(
                    company=self.company,
                    batch=batch,
                    run_line=line,
                    employee=line.employee,
                    claim_active=True,
                    employee_number=line.employee_number,
                    employee_name=line.employee_name,
                    national_id=line.employee.national_id,
                    employee_address=line.employee.address,
                    destination_type=PaymentDestination.IBAN,
                    account_holder_name=line.employee_name,
                    bank_name="Scale Test Payroll Bank",
                    bank_code="SCALE",
                    iban=iban,
                    salary_card_number="",
                    destination_fingerprint=sensitive_fingerprint(iban),
                    amount=line.net,
                    basic_salary=line.basic,
                    housing_allowance=_money(line.basic * D("0.20")),
                    other_earnings=_money(line.allowances - _money(line.basic * D("0.20")) + line.overtime_amount + line.other_earnings),
                    deductions=line.total_deductions,
                    status=SalaryPaymentRowStatus.PAID,
                    transaction_reference=f"DEMO-SCALE-WPS-{run.period_start:%Y%m}-{index:05d}",
                    attempt_count=1,
                    paid_at=self.now,
                    last_result_at=self.now,
                )

        _bulk_create(SalaryPaymentRow, rows(), batch_size=self.batch_size)
        actual_count = batch.rows.filter(run_line_id__in=[line.pk for line in lines]).count()
        SalaryPaymentBatch.objects.filter(pk=batch.pk).update(
            employee_count=actual_count,
            total_amount=total,
            paid_amount=total,
            source_fingerprint=_stable_sha256("wps", run.period_start, actual_count, total),
        )

    def _ensure_suppliers(self) -> list[ManpowerSupplier]:
        codes = [f"{SUPPLIER_PREFIX}{index:03d}" for index in range(1, self.profile.suppliers + 1)]
        existing = set(ManpowerSupplier.objects.for_company(self.company).filter(code__in=codes).values_list("code", flat=True))
        rows = (
            ManpowerSupplier(
                company=self.company,
                code=code,
                name=f"Scale Manpower Supplier {index:03d}",
                status=SupplierStatus.ACTIVE,
                contact_person=f"Scale Supplier Contact {index:03d}",
                phone=f"+96656{index:07d}",
                email=f"scale-supplier-{index:03d}@example.invalid",
                payment_terms="30 days",
                address=f"TEST DATA · Scale Supplier {index:03d}, Saudi Arabia",
                notes=SOURCE_MARKER,
            )
            for index, code in enumerate(codes, start=1)
            if code not in existing
        )
        _bulk_create(ManpowerSupplier, rows, batch_size=self.batch_size)
        return list(ManpowerSupplier.objects.for_company(self.company).filter(code__in=codes).order_by("code"))

    def _ensure_projects(self) -> list[Project]:
        codes = [f"{PROJECT_PREFIX}{index:03d}" for index in range(1, self.profile.projects + 1)]
        existing = set(Project.objects.for_company(self.company).filter(code__in=codes).values_list("code", flat=True))
        rows = (
            Project(
                company=self.company,
                code=code,
                name=f"Scale Test Project {index:03d}",
                client_name=f"Scale Client {(index - 1) % 9 + 1:02d}",
                location=("Dammam", "Jubail", "Riyadh", "Khobar", "Dhahran")[index % 5],
                start_date=self.origin,
                manager_name=f"Scale Project Manager {index:03d}",
                status=Project.Status.ACTIVE,
                notes=SOURCE_MARKER,
                created_by=self.user,
                updated_by=self.user,
            )
            for index, code in enumerate(codes, start=1)
            if code not in existing
        )
        _bulk_create(Project, rows, batch_size=self.batch_size)
        return list(Project.objects.for_company(self.company).filter(code__in=codes).order_by("code"))

    def _ensure_rental_workers(self, suppliers: list[ManpowerSupplier], projects: list[Project]) -> list[RentalWorker]:
        numbers = [f"{RENTAL_PREFIX}{index:05d}" for index in range(1, self.profile.rental_workers + 1)]
        existing = set(RentalWorker.objects.for_company(self.company).filter(worker_number__in=numbers).values_list("worker_number", flat=True))

        def rows():
            for index, number in enumerate(numbers, start=1):
                if number in existing:
                    continue
                state = _rental_state(index, self.anchor_period, self.now)
                yield RentalWorker(
                    company=self.company,
                    worker_number=number,
                    full_name=f"Scale Rental Worker {index:05d}",
                    national_id=f"DEMO-SCALE-RQ-{index:08d}",
                    phone=f"+96657{index:07d}",
                    supplier=suppliers[(index - 1) % len(suppliers)],
                    status=state["status"],
                    notes=SOURCE_MARKER,
                    inactive_on=state["inactive_on"],
                    inactive_reason=state["inactive_reason"],
                    terminated_on=state["terminated_on"],
                    termination_reason=state["termination_reason"],
                    archived_at=state["archived_at"],
                    archived_reason=state["archived_reason"],
                )

        _bulk_create(RentalWorker, rows(), batch_size=self.batch_size)
        workers = list(
            RentalWorker.objects.for_company(self.company).filter(worker_number__in=numbers).select_related("supplier").order_by("worker_number")
        )
        self._ensure_worker_assignments(workers, projects)
        return workers

    def _ensure_worker_assignments(self, workers: list[RentalWorker], projects: list[Project]) -> None:
        worker_ids = [worker.pk for worker in workers]
        existing = set(
            WorkerAssignment.objects.for_company(self.company)
            .filter(worker_id__in=worker_ids, reason__startswith=SOURCE_MARKER)
            .values_list("worker_id", "effective_from")
        )

        def rows():
            for worker in workers:
                index = _numeric_suffix(worker.worker_number)
                project = projects[(index - 1) % len(projects)]
                next_project = projects[index % len(projects)]
                trade = RENTAL_TRADES[(index - 1) % len(RENTAL_TRADES)]
                rate = _rate(D("8.50") + D(index % 8) * D("0.75"))
                nonactive = worker.status in {RentalWorkerStatus.INACTIVE, RentalWorkerStatus.TERMINATED} or worker.archived_at
                final_end = self.final_scale_date if nonactive else None
                transfer = index % 10 == 0 and len(projects) > 1
                if transfer:
                    key = (worker.pk, self.origin)
                    if key not in existing:
                        yield WorkerAssignment(
                            company=self.company,
                            worker=worker,
                            project=project,
                            trade=trade,
                            rate_type=RentalRateType.HOURLY,
                            rate=rate,
                            effective_from=self.origin,
                            effective_to=self.transfer_date - timedelta(days=1),
                            change_type=AssignmentChangeType.ASSIGNMENT,
                            reason=f"{SOURCE_MARKER} initial project assignment",
                            end_reason=f"{SOURCE_MARKER} transfer",
                        )
                    key = (worker.pk, self.transfer_date)
                    if key not in existing:
                        yield WorkerAssignment(
                            company=self.company,
                            worker=worker,
                            project=next_project,
                            trade=trade,
                            rate_type=RentalRateType.HOURLY,
                            rate=_rate(rate + D("0.50")),
                            effective_from=self.transfer_date,
                            effective_to=final_end,
                            change_type=AssignmentChangeType.TRANSFER,
                            reason=f"{SOURCE_MARKER} transfer history",
                            end_reason=f"{SOURCE_MARKER} activity ended" if final_end else "",
                            release_disposition=ReleaseDisposition.INACTIVE if final_end else "",
                        )
                else:
                    key = (worker.pk, self.origin)
                    if key not in existing:
                        yield WorkerAssignment(
                            company=self.company,
                            worker=worker,
                            project=project,
                            trade=trade,
                            rate_type=RentalRateType.HOURLY,
                            rate=rate,
                            effective_from=self.origin,
                            effective_to=final_end,
                            change_type=AssignmentChangeType.ASSIGNMENT,
                            reason=f"{SOURCE_MARKER} project assignment",
                            end_reason=f"{SOURCE_MARKER} activity ended" if final_end else "",
                            release_disposition=ReleaseDisposition.INACTIVE if final_end else "",
                        )

        _bulk_create(WorkerAssignment, rows(), batch_size=self.batch_size)

    def _rental_assignment_map(self, workers: list[RentalWorker]) -> dict[object, list[WorkerAssignment]]:
        result: dict[object, list[WorkerAssignment]] = {worker.pk: [] for worker in workers}
        rows = (
            WorkerAssignment.objects.for_company(self.company)
            .filter(worker_id__in=result, cancelled_at__isnull=True)
            .select_related("project", "worker", "worker__supplier")
            .order_by("worker_id", "effective_from")
        )
        for row in rows:
            result[row.worker_id].append(row)
        return result

    @staticmethod
    def _assignment_for_period(rows: list[WorkerAssignment], period_start: date) -> WorkerAssignment:
        period_end = _month_end(period_start)
        candidates = [
            row for row in rows
            if row.effective_from <= period_end and (row.effective_to is None or row.effective_to >= period_start)
        ]
        if not candidates:
            raise ValidationError({"profile": f"Scale rental worker has no assignment for {period_start:%Y-%m}."})
        return max(candidates, key=lambda row: row.effective_from)

    def _ensure_rental_timesheets(
        self,
        workers: list[RentalWorker],
        assignments: dict[object, list[WorkerAssignment]],
        projects: list[Project],
    ) -> dict[tuple[object, date], RentalTimesheetPeriod]:
        project_ids = [project.pk for project in projects]
        existing = set(
            RentalTimesheetPeriod.objects.for_company(self.company)
            .filter(project_id__in=project_ids, period_start__in=self.months)
            .values_list("project_id", "period_start")
        )

        def period_rows():
            for project in projects:
                for period_start in self.months:
                    if (project.pk, period_start) in existing:
                        continue
                    yield RentalTimesheetPeriod(
                        company=self.company,
                        project=project,
                        period_start=period_start,
                        period_end=_month_end(period_start),
                        status=RentalTimesheetStatus.LOCKED,
                        revision=1,
                        submitted_at=self.now,
                        submitted_by=self.user,
                        approved_at=self.now,
                        approved_by=self.user,
                        locked_at=self.now,
                        locked_by=self.user,
                    )

        _bulk_create(RentalTimesheetPeriod, period_rows(), batch_size=self.batch_size)
        periods = {
            (row.project_id, row.period_start): row
            for row in RentalTimesheetPeriod.objects.for_company(self.company).filter(
                project_id__in=project_ids, period_start__in=self.months
            )
        }
        worker_ids = [worker.pk for worker in workers]
        existing_pairs = set(
            RentalTimesheetEntry.objects.for_company(self.company)
            .filter(period_id__in=[period.pk for period in periods.values()], worker_id__in=worker_ids)
            .values_list("period_id", "worker_id")
            .distinct()
        )

        def entry_rows():
            for worker in workers:
                index = _numeric_suffix(worker.worker_number)
                for period_start in self.months:
                    assignment = self._assignment_for_period(assignments[worker.pk], period_start)
                    period = periods[(assignment.project_id, period_start)]
                    if (period.pk, worker.pk) in existing_pairs:
                        continue
                    for work_date in _days(period_start):
                        hours, code = _rental_day_value(index, work_date)
                        yield RentalTimesheetEntry(
                            company=self.company,
                            period=period,
                            worker=worker,
                            assignment=assignment,
                            work_date=work_date,
                            regular_hours=hours,
                            code=code,
                            note=SOURCE_MARKER,
                            supplier_code=worker.supplier.code,
                            supplier_name=worker.supplier.name,
                            project_code=assignment.project.code,
                            project_name=assignment.project.name,
                            trade=assignment.trade,
                            rate_type=assignment.rate_type,
                            rate=assignment.rate,
                        )

        _bulk_create(RentalTimesheetEntry, entry_rows(), batch_size=self.batch_size)
        existing_ot = set(
            RentalTimesheetOvertime.objects.for_company(self.company)
            .filter(period_id__in=[period.pk for period in periods.values()], worker_id__in=worker_ids)
            .values_list("period_id", "worker_id")
        )

        def overtime_rows():
            for worker in workers:
                index = _numeric_suffix(worker.worker_number)
                if index % 4 != 0:
                    continue
                for period_start in self.months:
                    assignment = self._assignment_for_period(assignments[worker.pk], period_start)
                    period = periods[(assignment.project_id, period_start)]
                    if (period.pk, worker.pk) in existing_ot:
                        continue
                    metrics = _rental_month_metrics(index, period_start, assignment)
                    yield RentalTimesheetOvertime(
                        company=self.company,
                        period=period,
                        worker=worker,
                        assignment=assignment,
                        hours=metrics["overtime_hours"],
                        rate=metrics["overtime_rate"],
                        supplier_code=worker.supplier.code,
                        supplier_name=worker.supplier.name,
                        project_code=assignment.project.code,
                        project_name=assignment.project.name,
                        trade=assignment.trade,
                        rate_type=assignment.rate_type,
                    )

        _bulk_create(RentalTimesheetOvertime, overtime_rows(), batch_size=self.batch_size)
        self._ensure_rental_adjustments(workers, assignments)
        return periods

    def _ensure_rental_adjustments(
        self,
        workers: list[RentalWorker],
        assignments: dict[object, list[WorkerAssignment]],
    ) -> None:
        specs: list[tuple[RentalWorker, WorkerAssignment, date, str, Decimal, str]] = []
        refs: list[str] = []
        for worker in workers:
            index = _numeric_suffix(worker.worker_number)
            for period_start in self.months:
                assignment = self._assignment_for_period(assignments[worker.pk], period_start)
                if index % 23 == 0:
                    refs.append(f"DEMO-SCALE-RADJ-{period_start:%Y%m}-{index:05d}-ADV")
                    specs.append((worker, assignment, period_start, RentalAdjustmentType.ADVANCE, D("120"), refs[-1]))
                if index % 17 == 0:
                    refs.append(f"DEMO-SCALE-RADJ-{period_start:%Y%m}-{index:05d}-BON")
                    specs.append((worker, assignment, period_start, RentalAdjustmentType.BONUS, D("125"), refs[-1]))
                if index % 19 == 0:
                    refs.append(f"DEMO-SCALE-RADJ-{period_start:%Y%m}-{index:05d}-FINE")
                    specs.append((worker, assignment, period_start, RentalAdjustmentType.FINE, D("80"), refs[-1]))
        existing = set(RentalAdjustment.objects.for_company(self.company).filter(reference__in=refs).values_list("reference", flat=True))

        def rows():
            for worker, assignment, period_start, adjustment_type, amount, reference in specs:
                if reference in existing:
                    continue
                yield RentalAdjustment(
                    company=self.company,
                    worker=worker,
                    supplier=worker.supplier,
                    project=assignment.project,
                    assignment=assignment,
                    transaction_date=period_start + timedelta(days=14),
                    period_start=period_start,
                    adjustment_type=adjustment_type,
                    amount=amount,
                    reason=f"{SOURCE_MARKER} {adjustment_type}",
                    reference=reference,
                    status=RentalAdjustmentStatus.APPROVED,
                    worker_number=worker.worker_number,
                    worker_name=worker.full_name,
                    supplier_code=worker.supplier.code,
                    supplier_name=worker.supplier.name,
                    project_code=assignment.project.code,
                    project_name=assignment.project.name,
                    trade=assignment.trade,
                    rate_type=assignment.rate_type,
                    rate=assignment.rate,
                    submitted_at=self.now,
                    submitted_by=self.user,
                    approved_at=self.now,
                    approved_by=self.user,
                )

        _bulk_create(RentalAdjustment, rows(), batch_size=self.batch_size)

    def _ensure_rental_financial_history(
        self,
        workers: list[RentalWorker],
        assignments: dict[object, list[WorkerAssignment]],
        periods: dict[tuple[object, date], RentalTimesheetPeriod],
    ) -> dict[tuple[object, object, date], SupplierSettlement]:
        groups: dict[tuple[object, object, date], list[tuple[RentalWorker, WorkerAssignment, dict]]] = {}
        for worker in workers:
            index = _numeric_suffix(worker.worker_number)
            for period_start in self.months:
                assignment = self._assignment_for_period(assignments[worker.pk], period_start)
                metrics = _rental_month_metrics(index, period_start, assignment)
                key = (assignment.project_id, worker.supplier_id, period_start)
                groups.setdefault(key, []).append((worker, assignment, metrics))

        existing_keys = set(
            SupplierSettlement.objects.for_company(self.company)
            .filter(period_start__in=self.months, project_id__in={key[0] for key in groups})
            .values_list("project_id", "supplier_id", "period_start")
        )

        def settlement_rows():
            for key, group in groups.items():
                project_id, supplier_id, period_start = key
                if key in existing_keys:
                    continue
                first_worker, assignment, _metrics = group[0]
                supplier = first_worker.supplier
                project = assignment.project
                total_regular = sum((row[2]["regular_hours"] for row in group), D("0"))
                total_days = sum(int(row[2]["work_days"]) for row in group)
                total_ot_hours = sum((row[2]["overtime_hours"] for row in group), D("0"))
                total_base = _money(sum((row[2]["base_amount"] for row in group), D("0")))
                total_ot = _money(sum((row[2]["overtime_amount"] for row in group), D("0")))
                adj_earn = _money(sum((row[2]["adjustment_earnings"] for row in group), D("0")))
                adj_ded = _money(sum((row[2]["adjustment_deductions"] for row in group), D("0")))
                gross = _money(total_base + total_ot)
                net = _money(gross + adj_earn - adj_ded)
                project_index = _numeric_suffix(project.code)
                supplier_index = _numeric_suffix(supplier.code)
                yield SupplierSettlement(
                    company=self.company,
                    settlement_number=f"DEMO-SCALE-SET-{period_start:%Y%m}-{project_index:03d}-{supplier_index:03d}",
                    period_start=period_start,
                    period_end=_month_end(period_start),
                    project=project,
                    supplier=supplier,
                    source_timesheet=periods[(project_id, period_start)],
                    source_timesheet_revision=periods[(project_id, period_start)].revision,
                    status=RentalSettlementStatus.CLOSED,
                    revision=1,
                    calculation_version=1,
                    source_fingerprint=_stable_sha256("rental", project_id, supplier_id, period_start),
                    snapshot_fingerprint=_stable_sha256("rental-snapshot", project_id, supplier_id, period_start, net),
                    project_code=project.code,
                    project_name=project.name,
                    supplier_code=supplier.code,
                    supplier_name=supplier.name,
                    worker_count=len(group),
                    total_regular_hours=total_regular,
                    total_work_days=total_days,
                    total_overtime_hours=total_ot_hours,
                    total_base=total_base,
                    total_overtime=total_ot,
                    total_gross=gross,
                    total_adjustment_earnings=adj_earn,
                    total_adjustment_deductions=adj_ded,
                    total_net=net,
                    calculated_at=self.now,
                    calculated_by=self.user,
                    submitted_at=self.now,
                    submitted_by=self.user,
                    approved_at=self.now,
                    approved_by=self.user,
                    reviewer_note=f"{SOURCE_MARKER} approved synthetic benchmark history",
                    closed_at=self.now,
                    closed_by=self.user,
                )

        _bulk_create(SupplierSettlement, settlement_rows(), batch_size=self.batch_size)
        settlements = {
            (row.project_id, row.supplier_id, row.period_start): row
            for row in SupplierSettlement.objects.for_company(self.company).filter(
                period_start__in=self.months,
                project_id__in={key[0] for key in groups},
                supplier_id__in={key[1] for key in groups},
            )
            if (row.project_id, row.supplier_id, row.period_start) in groups
        }
        # Reconcile aggregate snapshots on every run. This matters when a larger
        # profile (benchmark) expands a previously seeded smaller profile
        # (realistic): existing settlement headers must grow with the newly
        # added worker lines instead of keeping the older totals.
        settlement_updates = []
        for key, group in groups.items():
            settlement = settlements[key]
            total_regular = sum((row[2]["regular_hours"] for row in group), D("0"))
            total_days = sum(int(row[2]["work_days"]) for row in group)
            total_ot_hours = sum((row[2]["overtime_hours"] for row in group), D("0"))
            total_base = _money(sum((row[2]["base_amount"] for row in group), D("0")))
            total_ot = _money(sum((row[2]["overtime_amount"] for row in group), D("0")))
            adj_earn = _money(sum((row[2]["adjustment_earnings"] for row in group), D("0")))
            adj_ded = _money(sum((row[2]["adjustment_deductions"] for row in group), D("0")))
            gross = _money(total_base + total_ot)
            net = _money(gross + adj_earn - adj_ded)
            settlement.worker_count = len(group)
            settlement.total_regular_hours = total_regular
            settlement.total_work_days = total_days
            settlement.total_overtime_hours = total_ot_hours
            settlement.total_base = total_base
            settlement.total_overtime = total_ot
            settlement.total_gross = gross
            settlement.total_adjustment_earnings = adj_earn
            settlement.total_adjustment_deductions = adj_ded
            settlement.total_net = net
            settlement.snapshot_fingerprint = _stable_sha256(
                "rental-snapshot", settlement.project_id, settlement.supplier_id, settlement.period_start, net
            )
            settlement_updates.append(settlement)
        if settlement_updates:
            SupplierSettlement.objects.bulk_update(
                settlement_updates,
                [
                    "worker_count",
                    "total_regular_hours",
                    "total_work_days",
                    "total_overtime_hours",
                    "total_base",
                    "total_overtime",
                    "total_gross",
                    "total_adjustment_earnings",
                    "total_adjustment_deductions",
                    "total_net",
                    "snapshot_fingerprint",
                ],
                batch_size=self.batch_size,
            )

        settlement_ids = [row.pk for row in settlements.values()]
        existing_lines = set(
            SupplierSettlementLine.objects.for_company(self.company)
            .filter(settlement_id__in=settlement_ids)
            .values_list("settlement_id", "worker_id")
        )

        def line_rows():
            for key, group in groups.items():
                settlement = settlements[key]
                for worker, assignment, metrics in group:
                    if (settlement.pk, worker.pk) in existing_lines:
                        continue
                    yield SupplierSettlementLine(
                        company=self.company,
                        settlement=settlement,
                        worker=worker,
                        worker_number=worker.worker_number,
                        worker_name=worker.full_name,
                        supplier_code=worker.supplier.code,
                        supplier_name=worker.supplier.name,
                        project_code=assignment.project.code,
                        project_name=assignment.project.name,
                        trade_summary=assignment.trade,
                        rate_summary=f"{assignment.rate_type.title()} SAR {assignment.rate}",
                        regular_hours=metrics["regular_hours"],
                        work_days=metrics["work_days"],
                        overtime_hours=metrics["overtime_hours"],
                        base_amount=metrics["base_amount"],
                        overtime_amount=metrics["overtime_amount"],
                        gross_amount=metrics["gross_amount"],
                        adjustment_earnings=metrics["adjustment_earnings"],
                        adjustment_deductions=metrics["adjustment_deductions"],
                        net_amount=metrics["net_amount"],
                    )

        _bulk_create(SupplierSettlementLine, line_rows(), batch_size=self.batch_size)
        self._ensure_supplier_payments(settlements)
        return settlements

    def _ensure_supplier_payments(self, settlements: dict[tuple[object, object, date], SupplierSettlement]) -> None:
        payment_numbers = {
            settlement.pk: f"DEMO-SCALE-PAY-{settlement.period_start:%Y%m}-{_numeric_suffix(settlement.project_code):03d}-{_numeric_suffix(settlement.supplier_code):03d}"
            for settlement in settlements.values()
        }
        existing_numbers = set(
            SupplierPayment.objects.for_company(self.company).filter(payment_number__in=payment_numbers.values()).values_list("payment_number", flat=True)
        )

        def payment_rows():
            for settlement in settlements.values():
                number = payment_numbers[settlement.pk]
                if number in existing_numbers:
                    continue
                yield SupplierPayment(
                    company=self.company,
                    supplier=settlement.supplier,
                    payment_number=number,
                    payment_date=settlement.period_end,
                    method=SupplierPaymentMethod.BANK,
                    amount=settlement.total_net,
                    status=SupplierPaymentStatus.PAID,
                    transaction_reference=f"DEMO-SCALE-TXN-{settlement.period_start:%Y%m}-{_numeric_suffix(settlement.project_code):03d}-{_numeric_suffix(settlement.supplier_code):03d}",
                    note=f"{SOURCE_MARKER} full settlement payment",
                    supplier_code=settlement.supplier_code,
                    supplier_name=settlement.supplier_name,
                    paid_at=self.now,
                )

        _bulk_create(SupplierPayment, payment_rows(), batch_size=self.batch_size)
        payments = {
            row.payment_number: row
            for row in SupplierPayment.objects.for_company(self.company).filter(payment_number__in=payment_numbers.values())
        }

        # Existing payments must track an expanded settlement when realistic is
        # later promoted to benchmark. Keep the same deterministic payment
        # identity while reconciling its paid amount and supplier snapshot.
        payment_updates = []
        for settlement in settlements.values():
            payment = payments[payment_numbers[settlement.pk]]
            payment.amount = settlement.total_net
            payment.status = SupplierPaymentStatus.PAID
            payment.payment_date = settlement.period_end
            payment.supplier_code = settlement.supplier_code
            payment.supplier_name = settlement.supplier_name
            if payment.paid_at is None:
                payment.paid_at = self.now
            payment_updates.append(payment)
        if payment_updates:
            SupplierPayment.objects.bulk_update(
                payment_updates,
                ["amount", "status", "payment_date", "supplier_code", "supplier_name", "paid_at"],
                batch_size=self.batch_size,
            )

        allocations = {
            row.settlement_id: row
            for row in SupplierPaymentAllocation.objects.for_company(self.company).filter(settlement_id__in=list(payment_numbers))
        }
        missing_rows = (
            SupplierPaymentAllocation(
                company=self.company,
                payment=payments[payment_numbers[settlement.pk]],
                settlement=settlement,
                amount=settlement.total_net,
            )
            for settlement in settlements.values()
            if settlement.pk not in allocations
        )
        _bulk_create(SupplierPaymentAllocation, missing_rows, batch_size=self.batch_size)

        allocations = {
            row.settlement_id: row
            for row in SupplierPaymentAllocation.objects.for_company(self.company).filter(settlement_id__in=list(payment_numbers))
        }
        allocation_updates = []
        for settlement in settlements.values():
            allocation = allocations[settlement.pk]
            payment = payments[payment_numbers[settlement.pk]]
            allocation.payment = payment
            allocation.amount = settlement.total_net
            allocation_updates.append(allocation)
        if allocation_updates:
            SupplierPaymentAllocation.objects.bulk_update(
                allocation_updates,
                ["payment", "amount"],
                batch_size=self.batch_size,
            )

    def _verify(self, *, internal, workers, payroll_runs, settlements) -> dict[str, int | str]:
        employee_ids = [row.pk for row in internal]
        worker_ids = [row.pk for row in workers]
        period_ids = list(
            AttendancePeriod.objects.for_company(self.company).filter(period_start__in=self.months).values_list("pk", flat=True)
        )
        rental_period_ids = list(
            RentalTimesheetPeriod.objects.for_company(self.company).filter(period_start__in=self.months).values_list("pk", flat=True)
        )
        expected_internal_daily = self.profile.internal_employees * sum(monthrange(month.year, month.month)[1] for month in self.months)
        expected_rental_daily = self.profile.rental_workers * sum(monthrange(month.year, month.month)[1] for month in self.months)
        expected_monthly_internal = self.profile.internal_employees * self.profile.months
        expected_monthly_rental = self.profile.rental_workers * self.profile.months
        actual = {
            "internal_employees": len(internal),
            "rental_workers": len(workers),
            "internal_daily_rows": AttendanceEntry.objects.for_company(self.company).filter(period_id__in=period_ids, employee_id__in=employee_ids).count(),
            "rental_daily_rows": RentalTimesheetEntry.objects.for_company(self.company).filter(period_id__in=rental_period_ids, worker_id__in=worker_ids).count(),
            "payroll_lines": PayrollRunLine.objects.for_company(self.company).filter(run_id__in=[run.pk for run in payroll_runs.values()], employee_id__in=employee_ids).count(),
            "salary_payment_rows": SalaryPaymentRow.objects.for_company(self.company).filter(batch__run_id__in=[run.pk for run in payroll_runs.values()], employee_id__in=employee_ids).count(),
            "settlement_lines": SupplierSettlementLine.objects.for_company(self.company).filter(settlement_id__in=[row.pk for row in settlements.values()], worker_id__in=worker_ids).count(),
            "supplier_payments": SupplierPayment.objects.for_company(self.company).filter(payment_number__startswith="DEMO-SCALE-PAY-").count(),
        }
        minimums = {
            "internal_employees": self.profile.internal_employees,
            "rental_workers": self.profile.rental_workers,
            "internal_daily_rows": expected_internal_daily,
            "rental_daily_rows": expected_rental_daily,
            "payroll_lines": expected_monthly_internal,
            "salary_payment_rows": expected_monthly_internal,
            "settlement_lines": expected_monthly_rental,
            "supplier_payments": len(settlements),
        }
        short = {key: (actual[key], minimum) for key, minimum in minimums.items() if actual[key] < minimum}
        if short:
            details = ", ".join(f"{key}={value}/{minimum}" for key, (value, minimum) in short.items())
            raise ValidationError({"profile": f"Scale seed verification failed: {details}. Rerun the same profile to resume safely."})
        return {
            "profile": self.profile.name,
            "months": self.profile.months,
            **actual,
        }


def seed_payroll_scale_data(*, company, actor, anchor_period: date, profile_name: str, batch_size: int = 5000) -> dict[str, int | str]:
    profile = get_scale_profile(profile_name)
    return PayrollScaleSeeder(
        company=company,
        actor=actor,
        anchor_period=anchor_period,
        requested=profile,
        batch_size=batch_size,
    ).run()
