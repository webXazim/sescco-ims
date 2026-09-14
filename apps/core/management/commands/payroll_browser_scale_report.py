from __future__ import annotations

import json
from datetime import date
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_can_workspace
from apps.accounts.roles import Workspace
from apps.core.models import Company
from apps.core.management.reports import build_report_page
from apps.core.management.selectors import management_approval_page_context, management_audit_page_context
from apps.core.selectors.record_management import record_management_page_context
from apps.documents.selectors.documents import document_page_context
from apps.internal_payroll.models import AttendancePeriod, BankExportChannel, InternalEmployee, SalaryPaymentBatch
from apps.internal_payroll.selectors.attendance import attendance_period_context
from apps.internal_payroll.selectors.organization import employees_for_company, serialize_employee
from apps.internal_payroll.selectors.payroll import payroll_adjustment_page_context, payroll_run_page_context
from apps.internal_payroll.selectors.payment import (
    salary_payment_batch_rows_context,
    salary_payment_readiness_page_context,
    salary_payment_shell_context,
)
from apps.internal_payroll.selectors.salary import current_salary_structures_for_company, serialize_salary_structure
from apps.rental_manpower.models import RentalTimesheetPeriod, RentalWorker
from apps.rental_manpower.project_adapter import project_public_id
from apps.rental_manpower.selectors.assignments import assignments_for_company, serialized_assignment_activity
from apps.rental_manpower.selectors.masters import serialize_worker, workers_for_company
from apps.rental_manpower.selectors.settlements import rental_adjustment_page_context
from apps.rental_manpower.selectors.timesheets import rental_timesheet_context


class Command(BaseCommand):
    help = "Certify bounded Payroll payload/query behavior against realistic or benchmark-scale data."

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--period", default="", help="YYYY-MM. Defaults to the largest seeded Internal attendance period.")
        parser.add_argument("--query", default="DEMO", help="High-cardinality search probe shared by seeded Internal DEMO and Rental RDEMO records; minimum 2 characters.")
        parser.add_argument("--require-benchmark-volume", action="store_true")
        parser.add_argument("--fail-on-limits", action="store_true")
        parser.add_argument("--max-payload-bytes", type=int, default=2_500_000)
        parser.add_argument("--max-context-queries", type=int, default=60)

    def _company(self, slug: str):
        qs = Company.objects.filter(is_active=True).order_by("name")
        if slug:
            try:
                return qs.get(slug=slug)
            except Company.DoesNotExist as exc:
                raise CommandError(f"Active company not found: {slug}") from exc
        rows = list(qs[:2])
        if len(rows) != 1:
            raise CommandError("Specify --company-slug unless exactly one active company exists.")
        return rows[0]

    @staticmethod
    def _parse_period(raw: str) -> date | None:
        raw = (raw or "").strip()
        if not raw:
            return None
        try:
            value = date.fromisoformat(f"{raw}-01" if len(raw) == 7 else raw)
        except ValueError as exc:
            raise CommandError("--period must use YYYY-MM.") from exc
        if value.day != 1:
            raise CommandError("--period must identify a calendar month.")
        return value

    @staticmethod
    def _payload_size(payload) -> int:
        return len(json.dumps(payload, cls=DjangoJSONEncoder, separators=(",", ":")).encode("utf-8"))

    def _measure(self, label: str, fn):
        started = perf_counter()
        with CaptureQueriesContext(connection) as captured:
            payload = fn()
        elapsed_ms = (perf_counter() - started) * 1000
        payload_bytes = self._payload_size(payload)
        queries = len(captured)
        self.stdout.write(
            f"  {label}: {queries} queries · {elapsed_ms:.1f} ms · {payload_bytes / 1024:.1f} KiB"
        )
        return payload, queries, payload_bytes

    @staticmethod
    def _salary_structure_page(*, company, query: str) -> dict[str, object]:
        employees = list(employees_for_company(company=company, query=query, archived=False)[:100])
        employee_ids = [row.pk for row in employees]
        structures = current_salary_structures_for_company(company=company).filter(employee_id__in=employee_ids)
        by_employee: dict[str, object] = {}
        for structure in structures:
            key = str(structure.employee_id)
            if key not in by_employee:
                by_employee[key] = serialize_salary_structure(structure)
        return {
            "surface": "salary_structure_directory_page",
            "results": [
                {"employee": serialize_employee(employee), "structure": by_employee.get(str(employee.pk))}
                for employee in employees
            ],
        }

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        query = str(options["query"] or "").strip()
        if len(query) < 2:
            raise CommandError("--query must contain at least 2 characters.")
        requested_period = self._parse_period(options["period"])

        internal_count = InternalEmployee.objects.for_company(company).count()
        rental_count = RentalWorker.objects.for_company(company).count()
        self.stdout.write(
            f"Payroll browser-scale report · {company.name} · "
            f"{internal_count:,} Internal · {rental_count:,} Rental"
        )

        errors: list[str] = []
        if options["require_benchmark_volume"]:
            if internal_count < 2000:
                errors.append(f"Internal benchmark volume missing: {internal_count} < 2000.")
            if rental_count < 5000:
                errors.append(f"Rental benchmark volume missing: {rental_count} < 5000.")

        internal_period = None
        if requested_period:
            internal_period = AttendancePeriod.objects.for_company(company).filter(period_start=requested_period).first()
        else:
            internal_period = (
                AttendancePeriod.objects.for_company(company)
                .annotate(volume=Count("entries"))
                .order_by("-volume", "-period_start")
                .first()
            )
        if internal_period is None:
            errors.append("No Internal attendance period is available for browser-scale certification.")
            period_start = requested_period or date.today().replace(day=1)
        else:
            period_start = internal_period.period_start

        max_payload = int(options["max_payload_bytes"])
        max_queries = int(options["max_context_queries"])

        def check(label: str, payload, queries: int, payload_bytes: int, *, row_count: int | None = None, max_rows: int = 100):
            if row_count is not None and row_count > max_rows:
                errors.append(f"{label} row bound exceeded: {row_count} > {max_rows}.")
            if queries > max_queries:
                errors.append(f"{label} query budget exceeded: {queries} > {max_queries}.")
            if payload_bytes > max_payload:
                errors.append(f"{label} payload budget exceeded: {payload_bytes} > {max_payload} bytes.")

        if internal_period is not None:
            attendance, qcount, pbytes = self._measure(
                "Internal attendance page (100)",
                lambda: attendance_period_context(
                    company=company,
                    period_start=period_start,
                    page=1,
                    page_size=100,
                    include_summary=False,
                ),
            )
            check("Internal attendance", attendance, qcount, pbytes, row_count=len(attendance.get("roster", [])))

        employee_page, qcount, pbytes = self._measure(
            "Internal employee search page (100)",
            lambda: [serialize_employee(row) for row in employees_for_company(company=company, query=query)[:100]],
        )
        check("Internal employee search", employee_page, qcount, pbytes, row_count=len(employee_page))

        worker_page, qcount, pbytes = self._measure(
            "Rental worker search page (100)",
            lambda: [serialize_worker(row) for row in workers_for_company(company=company, query=query)[:100]],
        )
        check("Rental worker search", worker_page, qcount, pbytes, row_count=len(worker_page))

        rental_adjustments, qcount, pbytes = self._measure(
            "Rental worker adjustments page (100)",
            lambda: rental_adjustment_page_context(
                company=company, period_start=period_start, page=1, page_size=100, search=query
            ),
        )
        check("Rental worker adjustments", rental_adjustments, qcount, pbytes, row_count=len(rental_adjustments.get("results", [])))

        assignment_payload, qcount, pbytes = self._measure(
            "Rental assignment activity segments (100)",
            lambda: serialized_assignment_activity(
                company=company,
                assignments=list(
                    assignments_for_company(company=company, query=query)
                    .order_by("-effective_from", "-created_at")[:100]
                ),
            ),
        )
        check(
            "Rental assignment activity",
            assignment_payload,
            qcount,
            pbytes,
            row_count=len(assignment_payload),
            max_rows=200,
        )

        rental_period = (
            RentalTimesheetPeriod.objects.for_company(company)
            .filter(period_start=period_start)
            .select_related("project")
            .annotate(volume=Count("entries"))
            .order_by("-volume", "project__code")
            .first()
        )
        if rental_period is None:
            errors.append(f"No Rental timesheet period exists for {period_start:%Y-%m}.")
        else:
            project_id = project_public_id(rental_period.project)
            rental_page, qcount, pbytes = self._measure(
                "Rental project timesheet page (100)",
                lambda: rental_timesheet_context(
                    company=company,
                    project_id=project_id,
                    period_start=period_start,
                    page=1,
                    page_size=100,
                    include_summary=False,
                ),
            )
            check("Rental project timesheet", rental_page, qcount, pbytes, row_count=len(rental_page.get("roster", [])))

        # 1.0.77 final certification: measure every high-cardinality Internal/shared surface
        # introduced by the 1.0.71-1.0.76 scale cutovers, not only the original 1.0.70 paths.
        memberships = list(
            CompanyMembership.objects.select_related("user", "company")
            .filter(company=company, is_active=True, user__is_active=True)
            .order_by("role", "user__username")
        )
        internal_memberships = [row for row in memberships if membership_can_workspace(row, Workspace.INTERNAL)]
        membership = internal_memberships[0] if internal_memberships else (memberships[0] if memberships else None)
        if options["require_benchmark_volume"] and membership is None:
            errors.append("Benchmark company has no active Payroll membership for document/payment certification.")

        salary_page, qcount, pbytes = self._measure(
            "Salary setup employee structures page (100)",
            lambda: self._salary_structure_page(company=company, query=query),
        )
        check("Salary setup employee structures", salary_page, qcount, pbytes, row_count=len(salary_page.get("results", [])))

        payroll_page, qcount, pbytes = self._measure(
            "Payroll run page (100)",
            lambda: payroll_run_page_context(
                company=company, period_start=period_start, membership=membership, page=1, page_size=100, search=query
            ),
        )
        check("Payroll run", payroll_page, qcount, pbytes, row_count=len(payroll_page.get("rows", [])))

        adjustment_page, qcount, pbytes = self._measure(
            "Internal adjustment register (100)",
            lambda: payroll_adjustment_page_context(
                company=company, period_start=period_start, page=1, page_size=100, search=query, view="register"
            ),
        )
        check("Internal adjustment register", adjustment_page, qcount, pbytes, row_count=len(adjustment_page.get("results", [])))

        balance_page, qcount, pbytes = self._measure(
            "Internal advance balances (100)",
            lambda: payroll_adjustment_page_context(
                company=company, period_start=period_start, page=1, page_size=100, search=query, view="balances"
            ),
        )
        check("Internal advance balances", balance_page, qcount, pbytes, row_count=len(balance_page.get("results", [])))

        payment_shell, qcount, pbytes = self._measure(
            "Salary payment compact shell",
            lambda: salary_payment_shell_context(company=company, period_start=period_start, membership=membership),
        )
        check("Salary payment compact shell", payment_shell, qcount, pbytes, row_count=len(payment_shell.get("batches", [])), max_rows=100)

        bank_page, qcount, pbytes = self._measure(
            "Salary payment readiness / bank (100)",
            lambda: salary_payment_readiness_page_context(
                company=company, period_start=period_start, membership=membership, channel=BankExportChannel.BANK_CSV,
                page=1, page_size=100, search=query, status="All"
            ),
        )
        check("Salary payment readiness / bank", bank_page, qcount, pbytes, row_count=len((bank_page.get("readiness") or {}).get("employees", [])))

        wps_page, qcount, pbytes = self._measure(
            "Salary payment readiness / WPS (100)",
            lambda: salary_payment_readiness_page_context(
                company=company, period_start=period_start, membership=membership, channel=BankExportChannel.WPS,
                page=1, page_size=100, search=query, status="All"
            ),
        )
        check("Salary payment readiness / WPS", wps_page, qcount, pbytes, row_count=len((wps_page.get("readiness") or {}).get("employees", [])))

        batch = SalaryPaymentBatch.objects.for_company(company).filter(run__period_start=period_start).order_by("-prepared_at").first()
        if batch is not None:
            batch_page, qcount, pbytes = self._measure(
                "Salary payment batch rows (100)",
                lambda: salary_payment_batch_rows_context(
                    company=company, batch_id=batch.pk, membership=membership, page=1, page_size=100, search=query, status="All"
                ),
            )
            check("Salary payment batch rows", batch_page, qcount, pbytes, row_count=len(batch_page.get("rows", [])))

        if membership is not None:
            docs_page, qcount, pbytes = self._measure(
                "Documents page (100)",
                lambda: document_page_context(
                    company=company, membership=membership, workspace="internal", query=query, page=1, page_size=100
                ),
            )
            check("Documents", docs_page, qcount, pbytes, row_count=len(docs_page.get("documents", [])))

        report_page, qcount, pbytes = self._measure(
            "Internal report page (100)",
            lambda: build_report_page(
                company=company, report_type="internal-payroll", period_start=period_start, workspace="internal",
                query=query, page=1, page_size=100
            ),
        )
        check("Internal report", report_page, qcount, pbytes, row_count=len(report_page.get("rows", [])))

        wps_report_page, qcount, pbytes = self._measure(
            "WPS report page (100)",
            lambda: build_report_page(
                company=company, report_type="wps", period_start=period_start, workspace="internal",
                query="", page=1, page_size=100
            ),
        )
        check("WPS report", wps_report_page, qcount, pbytes, row_count=len(wps_report_page.get("rows", [])))

        wps_report_search, qcount, pbytes = self._measure(
            "WPS report search (100)",
            lambda: build_report_page(
                company=company, report_type="wps", period_start=period_start, workspace="internal",
                query=query, page=1, page_size=100
            ),
        )
        check("WPS report search", wps_report_search, qcount, pbytes, row_count=len(wps_report_search.get("rows", [])))

        archive_page, qcount, pbytes = self._measure(
            "Archive page (100)",
            lambda: record_management_page_context(
                company=company, workspace="internal", bucket="archive", page=1, page_size=100, query=query
            ),
        )
        check("Archive", archive_page, qcount, pbytes, row_count=len(archive_page.get("records", [])))

        trash_page, qcount, pbytes = self._measure(
            "Delete recovery page (100)",
            lambda: record_management_page_context(
                company=company, workspace="internal", bucket="trash", page=1, page_size=100, query=query
            ),
        )
        check("Delete recovery", trash_page, qcount, pbytes, row_count=len(trash_page.get("records", [])))

        approval_page, qcount, pbytes = self._measure(
            "Management approvals page (100)",
            lambda: management_approval_page_context(company=company, filter_value="All", page=1, page_size=100),
        )
        check("Management approvals", approval_page, qcount, pbytes, row_count=len(approval_page.get("approvals", [])))

        audit_page, qcount, pbytes = self._measure(
            "Management audit page (100)",
            lambda: management_audit_page_context(company=company, query=query, page=1, page_size=100),
        )
        check("Management audit", audit_page, qcount, pbytes, row_count=len(audit_page.get("audit", [])))

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_limits"]:
                raise CommandError("Payroll browser-scale certification failed.")
            self.stdout.write(self.style.WARNING("Payroll browser-scale report completed with warnings."))
        else:
            self.stdout.write(self.style.SUCCESS("Payroll browser-scale limits passed."))
