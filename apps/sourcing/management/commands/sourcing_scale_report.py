from __future__ import annotations

import csv
import io
from time import perf_counter

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import Company
from apps.sourcing.exchange import read_import_rows
from apps.sourcing.management.scale_seed import SEED_PREFIX
from apps.sourcing.models import (
    SourcingManpowerSupplier,
    SourcingMaterial,
    SourcingTrade,
    SourcingVendor,
    SourcingVendorOffer,
    SourcingWorkforceOffer,
)
from apps.sourcing.selectors.manpower import manpower_directory_page
from apps.sourcing.selectors.material_finder import material_finder_page
from apps.sourcing.selectors.materials import material_directory_page, vendor_catalog_page
from apps.sourcing.selectors.trades import trade_directory_page
from apps.sourcing.selectors.vendors import vendor_directory_page
from apps.sourcing.selectors.workforce import workforce_catalog_page
from apps.sourcing.selectors.workforce_finder import workforce_finder_page

BENCHMARK_VOLUME = {
    "vendors": 10_000,
    "materials": 2_000,
    "vendor_offers": 50_000,
    "manpower_suppliers": 5_000,
    "trades": 250,
    "workforce_offers": 25_000,
}


class Command(BaseCommand):
    help = "Benchmark bounded Sourcing directories, finders, profile catalogs and import parsing at scale."

    def add_arguments(self, parser):
        parser.add_argument("--company-slug", default="")
        parser.add_argument("--query", default="SDEMO")
        parser.add_argument("--require-benchmark-volume", action="store_true")
        parser.add_argument("--fail-on-limits", action="store_true")
        parser.add_argument("--max-page-queries", type=int, default=12)
        parser.add_argument("--max-page-ms", type=int, default=1500)
        parser.add_argument("--max-import-parse-ms", type=int, default=2500)

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

    def _measure(self, label: str, fn):
        started = perf_counter()
        with CaptureQueriesContext(connection) as captured:
            rows = fn()
        elapsed_ms = (perf_counter() - started) * 1000
        self.stdout.write(f"  {label}: {len(captured)} queries · {elapsed_ms:.1f} ms · {len(rows)} rows")
        return len(captured), elapsed_ms, len(rows)

    def handle(self, *args, **options):
        company = self._company(options["company_slug"])
        query = str(options["query"] or "SDEMO").strip()
        if len(query) < 2:
            raise CommandError("--query must contain at least 2 characters.")

        counts = {
            "vendors": SourcingVendor.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}V").count(),
            "materials": SourcingMaterial.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}M").count(),
            "vendor_offers": SourcingVendorOffer.objects.for_company(company).filter(vendor__code__startswith=f"{SEED_PREFIX}V").count(),
            "manpower_suppliers": SourcingManpowerSupplier.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}P").count(),
            "trades": SourcingTrade.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}T").count(),
            "workforce_offers": SourcingWorkforceOffer.objects.for_company(company).filter(supplier__code__startswith=f"{SEED_PREFIX}P").count(),
        }
        self.stdout.write("Sourcing scale report · " + company.name + " · " + " · ".join(f"{k}={v:,}" for k, v in counts.items()))
        errors: list[str] = []
        if options["require_benchmark_volume"]:
            for key, minimum in BENCHMARK_VOLUME.items():
                if counts[key] < minimum:
                    errors.append(f"Benchmark volume missing: {key} {counts[key]} < {minimum}.")

        max_queries = int(options["max_page_queries"])
        max_ms = int(options["max_page_ms"])

        def check(label: str, measured):
            queries, elapsed, rows = measured
            if rows > 100:
                errors.append(f"{label} row bound exceeded: {rows} > 100.")
            if queries > max_queries:
                errors.append(f"{label} query budget exceeded: {queries} > {max_queries}.")
            if elapsed > max_ms:
                errors.append(f"{label} time budget exceeded: {elapsed:.1f} ms > {max_ms} ms.")

        def vendor_page():
            page = vendor_directory_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        def manpower_page():
            page = manpower_directory_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        def material_page():
            page = material_directory_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        def trade_page():
            page = trade_directory_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        def material_finder():
            page = material_finder_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        def workforce_finder():
            page = workforce_finder_page(company=company, params={"q": query, "page_size": 100}).page_obj
            return list(page.object_list)

        for label, fn in (
            ("Vendor directory search", vendor_page),
            ("Material directory search", material_page),
            ("Material Finder search", material_finder),
            ("Manpower directory search", manpower_page),
            ("Trade directory search", trade_page),
            ("Workforce Finder search", workforce_finder),
        ):
            check(label, self._measure(label, fn))

        vendor = SourcingVendor.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}V").order_by("code").first()
        if vendor:
            check("Vendor profile catalog", self._measure("Vendor profile catalog", lambda: vendor_catalog_page(company=company, vendor=vendor, page=1, page_size=100)[1]))
        supplier = SourcingManpowerSupplier.objects.for_company(company).filter(code__startswith=f"{SEED_PREFIX}P").order_by("code").first()
        if supplier:
            check("Manpower profile workforce", self._measure("Manpower profile workforce", lambda: workforce_catalog_page(company=company, supplier=supplier, page=1, page_size=100)[1]))

        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(["code", "name"])
        for i in range(5000):
            writer.writerow([f"SDEMO-PARSE-{i:05d}", f"SDEMO Parse Vendor {i:05d}"])
        payload = stream.getvalue().encode("utf-8")
        uploaded = SimpleUploadedFile("sourcing-benchmark.csv", payload, content_type="text/csv")
        started = perf_counter()
        _headers, records = read_import_rows(uploaded)
        parse_ms = (perf_counter() - started) * 1000
        self.stdout.write(f"  5,000-row import parser: {parse_ms:.1f} ms · {len(records)} rows")
        if len(records) != 5000:
            errors.append(f"Import parser row bound changed: {len(records)} != 5000.")
        if parse_ms > int(options["max_import_parse_ms"]):
            errors.append(f"Import parser time budget exceeded: {parse_ms:.1f} ms > {options['max_import_parse_ms']} ms.")

        if errors:
            for error in errors:
                self.stderr.write(f"ERROR: {error}")
            if options["fail_on_limits"]:
                raise CommandError("Sourcing scale certification failed.")
        self.stdout.write(self.style.SUCCESS("Sourcing scale certification complete."))
