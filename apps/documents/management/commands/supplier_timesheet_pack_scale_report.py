from __future__ import annotations

import json
from datetime import date
from time import perf_counter

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import Count
from django.test.utils import CaptureQueriesContext

from apps.core.models import Company
from apps.documents.printing import (
    build_supplier_timesheet_pack_print_context,
    build_supplier_timesheet_pack_worker_print_context,
)
from apps.documents.services.supplier_timesheet_pack import build_supplier_timesheet_pack_snapshot
from apps.rental_manpower.models import RentalTimesheetEntry, RentalTimesheetPeriod, RentalTimesheetStatus


DEFAULT_MAX_AGGREGATE_QUERIES = 2
DEFAULT_MAX_PRINT_QUERIES = 0
DEFAULT_MAX_SNAPSHOT_MIB = 8.0


class Command(BaseCommand):
    help = (
        "Measure Supplier Timesheet Pack v3 query count, immutable snapshot size and query-free print behavior "
        "against a real Locked Rental timesheet source."
    )

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--period", default="", help="Optional YYYY-MM month.")
        parser.add_argument("--project-code", default="", help="Optional exact project code.")
        parser.add_argument("--supplier-code", default="", help="Optional exact supplier code.")
        parser.add_argument("--min-workers", type=int, default=0, help="Fail when the selected source has fewer workers.")
        parser.add_argument("--max-aggregate-queries", type=int, default=DEFAULT_MAX_AGGREGATE_QUERIES)
        parser.add_argument("--max-print-queries", type=int, default=DEFAULT_MAX_PRINT_QUERIES)
        parser.add_argument("--max-snapshot-mib", type=float, default=DEFAULT_MAX_SNAPSHOT_MIB)
        parser.add_argument("--fail-on-limits", action="store_true")

    def _company(self, slug: str) -> Company:
        qs = Company.objects.filter(is_active=True).order_by("name")
        if slug:
            try:
                return qs.get(slug=slug.strip())
            except Company.DoesNotExist as exc:
                raise CommandError(f"Active company not found: {slug}") from exc
        rows = list(qs[:2])
        if len(rows) != 1:
            raise CommandError("Specify --company-slug unless exactly one active company exists.")
        return rows[0]

    @staticmethod
    def _period(raw: str) -> date | None:
        raw = str(raw or "").strip()
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
    def _measure(fn):
        started = perf_counter()
        with CaptureQueriesContext(connection) as captured:
            result = fn()
        return result, len(captured), (perf_counter() - started) * 1000

    def _largest_group(self, *, company: Company, period_start: date | None, project_code: str, supplier_code: str):
        qs = (
            RentalTimesheetEntry.objects.for_company(company)
            .filter(period__status=RentalTimesheetStatus.LOCKED)
        )
        if period_start:
            qs = qs.filter(period__period_start=period_start)
        if project_code:
            qs = qs.filter(period__project__code__iexact=project_code.strip())
        if supplier_code:
            qs = qs.filter(supplier_code__iexact=supplier_code.strip())
        row = (
            qs.values(
                "period_id",
                "period__period_start",
                "period__project__code",
                "period__project__name",
                "supplier_code",
                "supplier_name",
            )
            .annotate(worker_count=Count("worker_id", distinct=True))
            .order_by("-worker_count", "-period__period_start", "period__project__code", "supplier_code")
            .first()
        )
        if row is None:
            raise CommandError("No matching Locked Rental timesheet supplier source is available to certify.")
        return row

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        period_start = self._period(options["period"])
        group = self._largest_group(
            company=company,
            period_start=period_start,
            project_code=options["project_code"],
            supplier_code=options["supplier_code"],
        )
        period = (
            RentalTimesheetPeriod.objects.for_company(company)
            .select_related("project")
            .get(pk=group["period_id"])
        )
        supplier_code = str(group["supplier_code"] or "").strip().upper()

        self.stdout.write(
            "Supplier Timesheet Pack scale report · "
            f"{company.name} · {period.period_start:%Y-%m} · {period.project.code} · {supplier_code}"
        )

        snapshot, aggregate_queries, aggregate_ms = self._measure(
            lambda: build_supplier_timesheet_pack_snapshot(period, supplier_code=supplier_code)[0]
        )
        worker_count = int(snapshot["summary"]["worker_count"])
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        snapshot_bytes = len(encoded)
        snapshot_mib = snapshot_bytes / (1024 * 1024)

        print_context, print_queries, print_ms = self._measure(
            lambda: build_supplier_timesheet_pack_print_context(snapshot)
        )
        first_worker_id = snapshot["workers"][0]["worker_id"]
        worker_context, worker_queries, worker_ms = self._measure(
            lambda: build_supplier_timesheet_pack_worker_print_context(snapshot, worker_id=first_worker_id)
        )

        self.stdout.write(
            f"  Aggregate: {worker_count} workers · {aggregate_queries} queries · {aggregate_ms:.1f} ms"
        )
        self.stdout.write(
            f"  Snapshot: {snapshot_bytes:,} bytes · {snapshot_mib:.2f} MiB · "
            f"{len(snapshot['workers'])} worker sheets"
        )
        self.stdout.write(
            f"  Full print context: {print_queries} queries · {print_ms:.1f} ms · "
            f"{print_context['summary_page_count']} summary sections · {print_context['worker_page_count']} worker sections"
        )
        self.stdout.write(
            f"  Worker extract: {worker_queries} queries · {worker_ms:.1f} ms · "
            f"{len(worker_context['worker']['days'])} calendar rows"
        )

        errors: list[str] = []
        if worker_count < int(options["min_workers"]):
            errors.append(f"Worker volume below certification target: {worker_count} < {int(options['min_workers'])}.")
        if aggregate_queries > int(options["max_aggregate_queries"]):
            errors.append(
                f"Aggregator query budget exceeded: {aggregate_queries} > {int(options['max_aggregate_queries'])}."
            )
        if print_queries > int(options["max_print_queries"]):
            errors.append(f"Print query budget exceeded: {print_queries} > {int(options['max_print_queries'])}.")
        if worker_queries != 0:
            errors.append(f"Derived worker print must remain query-free: {worker_queries} queries observed.")
        if snapshot_mib > float(options["max_snapshot_mib"]):
            errors.append(
                f"Snapshot size budget exceeded: {snapshot_mib:.2f} MiB > {float(options['max_snapshot_mib']):.2f} MiB."
            )
        if print_context["worker_page_count"] != worker_count:
            errors.append("Printable worker count does not reconcile with snapshot worker_count.")
        if len(worker_context["worker"]["days"]) not in {28, 29, 30, 31}:
            errors.append("Derived worker print does not contain a complete calendar month.")

        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_limits"]:
                raise CommandError("Supplier Timesheet Pack scale certification failed.")
            self.stdout.write(self.style.WARNING("Supplier Timesheet Pack scale limits have warnings."))
        else:
            self.stdout.write(self.style.SUCCESS("Supplier Timesheet Pack scale limits passed."))
