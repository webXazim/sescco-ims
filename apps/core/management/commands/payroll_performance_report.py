from __future__ import annotations

from datetime import date
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext

from apps.core.models import Company
from apps.internal_payroll.models import AttendancePeriod
from apps.internal_payroll.selectors.attendance import attendance_period_context
from apps.internal_payroll.services.payroll import preview_payroll_run
from apps.rental_manpower.models import RentalTimesheetPeriod
from apps.rental_manpower.selectors.timesheets import rental_timesheet_context
from apps.rental_manpower.selectors.settlements import rental_settlement_context
from apps.rental_manpower.project_adapter import project_public_id


class Command(BaseCommand):
    help = "Measure high-cardinality Payroll read/preflight query counts and elapsed time."

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--period", default="", help="YYYY-MM. Defaults to the largest seeded Internal attendance period.")
        parser.add_argument("--fail-on-query-budget", action="store_true")
        parser.add_argument("--max-internal-queries", type=int, default=40)
        parser.add_argument("--max-rental-queries", type=int, default=40)

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

    def _measure(self, label: str, fn):
        started = perf_counter()
        with CaptureQueriesContext(connection) as captured:
            result = fn()
        elapsed_ms = (perf_counter() - started) * 1000
        query_count = len(captured)
        self.stdout.write(f"  {label}: {query_count} queries · {elapsed_ms:.1f} ms")
        return result, query_count, elapsed_ms

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        requested_period = self._parse_period(options["period"])

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
            raise CommandError("No Internal attendance period is available to benchmark.")
        period_start = internal_period.period_start

        rental_period = (
            RentalTimesheetPeriod.objects.for_company(company)
            .filter(period_start=period_start)
            .select_related("project")
            .annotate(volume=Count("entries"))
            .order_by("-volume", "project__code")
            .first()
        )

        self.stdout.write(f"Payroll performance report · {company.name} · {period_start:%Y-%m}")
        attendance_payload, attendance_queries, _ = self._measure(
            "Internal attendance context",
            lambda: attendance_period_context(company=company, period_start=period_start),
        )
        payroll_payload, payroll_queries, _ = self._measure(
            "Internal payroll preflight",
            lambda: preview_payroll_run(company=company, period_start=period_start),
        )
        self.stdout.write(
            f"    Internal volume: {len(attendance_payload.get('roster', []))} employees · "
            f"{len(payroll_payload.get('rows', []))} payroll rows"
        )

        rental_queries = 0
        if rental_period is not None:
            project_id = project_public_id(rental_period.project)
            rental_payload, timesheet_queries, _ = self._measure(
                "Rental timesheet context",
                lambda: rental_timesheet_context(
                    company=company, project_id=project_id, period_start=period_start
                ),
            )
            settlement_payload, settlement_queries, _ = self._measure(
                "Rental settlement context",
                lambda: rental_settlement_context(company=company, period_start=period_start),
            )
            rental_queries = max(timesheet_queries, settlement_queries)
            self.stdout.write(
                f"    Rental volume: {len(rental_payload.get('roster', []))} workers in largest project · "
                f"{len(settlement_payload.get('settlements', []))} settlement snapshots"
            )
        else:
            self.stdout.write(self.style.WARNING("  No Rental timesheet period exists for the selected month."))

        errors = []
        internal_budget = int(options["max_internal_queries"])
        rental_budget = int(options["max_rental_queries"])
        if max(attendance_queries, payroll_queries) > internal_budget:
            errors.append(
                f"Internal query budget exceeded: {max(attendance_queries, payroll_queries)} > {internal_budget}."
            )
        if rental_period is not None and rental_queries > rental_budget:
            errors.append(f"Rental query budget exceeded: {rental_queries} > {rental_budget}.")

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_query_budget"]:
                raise CommandError("Payroll performance query budget failed.")
        else:
            self.stdout.write(self.style.SUCCESS("Payroll query budgets are within the configured limits."))
