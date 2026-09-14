from __future__ import annotations

from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import Company
from apps.internal_payroll.selectors.organization import employees_for_company
from apps.rental_manpower.selectors.assignments import assignments_for_company
from apps.rental_manpower.selectors.masters import workers_for_company


class Command(BaseCommand):
    help = "Measure and optionally EXPLAIN the high-cardinality Payroll directory/search query plans."

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--query", default="DEMO", help="Search term used for employee/worker/assignment probes.")
        parser.add_argument("--rows", type=int, default=50, help="Rows to materialize per probe (1-100).")
        parser.add_argument("--explain", action="store_true", help="Print PostgreSQL EXPLAIN plans without ANALYZE.")

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

    def _probe(self, label: str, queryset, row_limit: int, explain: bool):
        if explain:
            if connection.vendor != "postgresql":
                self.stdout.write(self.style.WARNING(f"  {label}: EXPLAIN skipped; database is {connection.vendor}."))
            else:
                self.stdout.write(f"\n{label} EXPLAIN")
                self.stdout.write(queryset[:row_limit].explain(verbose=False, analyze=False, buffers=False))
        started = perf_counter()
        with CaptureQueriesContext(connection) as captured:
            rows = list(queryset[:row_limit])
        elapsed_ms = (perf_counter() - started) * 1000
        self.stdout.write(f"  {label}: {len(rows)} rows · {len(captured)} queries · {elapsed_ms:.1f} ms")
        return rows

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        query = str(options["query"] or "").strip()
        if len(query) < 2:
            raise CommandError("--query must contain at least 2 characters to match the production search contract.")
        row_limit = max(1, min(100, int(options["rows"] or 50)))
        explain = bool(options["explain"])

        self.stdout.write(f"Payroll search query report · {company.name} · q={query!r} · rows={row_limit}")
        self._probe(
            "Internal employees",
            employees_for_company(company=company, query=query, archived=False),
            row_limit,
            explain,
        )
        self._probe(
            "Rental workers",
            workers_for_company(company=company, query=query, archived=False),
            row_limit,
            explain,
        )
        self._probe(
            "Rental assignment activity",
            assignments_for_company(company=company, query=query).order_by("-effective_from", "-created_at"),
            row_limit,
            explain,
        )
        self.stdout.write(self.style.SUCCESS("Payroll search query report completed."))
