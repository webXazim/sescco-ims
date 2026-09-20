from __future__ import annotations

import io
import json
import threading
from datetime import date, timedelta
from decimal import Decimal

from django.core.management import call_command
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.documents.models import BusinessDocument, DocumentType
from apps.documents.printing import (
    SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE,
    build_supplier_timesheet_pack_print_context,
    build_supplier_timesheet_pack_worker_print_context,
)
from apps.documents.services.documents import finalize_business_document
from apps.documents.services.supplier_timesheet_pack import build_supplier_timesheet_pack_snapshot
from apps.projects.models import Project
from apps.rental_manpower.models import (
    ManpowerSupplier,
    RentalRateType,
    RentalTimesheetEntry,
    RentalTimesheetOvertime,
    RentalTimesheetPeriod,
    RentalTimesheetStatus,
    RentalWorker,
    WorkerAssignment,
)


CERTIFIED_WORKERS = 250
CERTIFIED_MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024


def _seed_pack_source(*, company: Company, user: User, supplier_code: str, worker_count: int):
    supplier = ManpowerSupplier.objects.create(
        company=company,
        code=supplier_code,
        name=f"{supplier_code} Scale Supplier",
        contact_person="Supplier Accounts",
        email="supplier-scale@example.com",
    )
    project = Project.objects.create(
        company=company,
        code=f"PRJ-{supplier_code[-5:]}",
        name=f"{supplier_code} Scale Project",
        start_date=date(2026, 6, 1),
        created_by=user,
        updated_by=user,
    )
    period = RentalTimesheetPeriod.objects.create(
        company=company,
        project=project,
        period_start=date(2026, 6, 1),
        period_end=date(2026, 6, 30),
        status=RentalTimesheetStatus.LOCKED,
        revision=11,
        locked_at=timezone.now(),
        locked_by=user,
    )

    RentalWorker.objects.bulk_create(
        [
            RentalWorker(
                company=company,
                worker_number=f"R-SCALE-{index:04d}",
                full_name=f"Scale Rental Worker {index:04d}",
                supplier=supplier,
            )
            for index in range(1, worker_count + 1)
        ],
        batch_size=500,
    )
    workers = list(
        RentalWorker.objects.filter(company=company, supplier=supplier).order_by("worker_number")
    )
    WorkerAssignment.objects.bulk_create(
        [
            WorkerAssignment(
                company=company,
                worker=worker,
                project=project,
                trade=("Mason", "Helper", "Carpenter", "Electrician")[(index - 1) % 4],
                rate_type=RentalRateType.HOURLY,
                rate=Decimal("15.00"),
                effective_from=date(2026, 6, 1),
                reason="Supplier Timesheet Pack scale certification",
            )
            for index, worker in enumerate(workers, start=1)
        ],
        batch_size=500,
    )
    assignments = {
        row.worker_id: row
        for row in WorkerAssignment.objects.filter(company=company, project=project, worker__supplier=supplier)
        .select_related("worker")
        .order_by("worker__worker_number")
    }

    entries = []
    overtime = []
    for index, worker in enumerate(workers, start=1):
        assignment = assignments[worker.pk]
        current = date(2026, 6, 1)
        while current <= date(2026, 6, 30):
            is_off = current.weekday() in {4, 5}
            entries.append(
                RentalTimesheetEntry(
                    company=company,
                    period=period,
                    worker=worker,
                    assignment=assignment,
                    work_date=current,
                    regular_hours=Decimal("0") if is_off else Decimal("8"),
                    code="OFF" if is_off else "",
                    note="",
                    supplier_code=supplier.code,
                    supplier_name=supplier.name,
                    project_code=project.code,
                    project_name=project.name,
                    trade=assignment.trade,
                    rate_type=assignment.rate_type,
                    rate=assignment.rate,
                )
            )
            current += timedelta(days=1)
        overtime.append(
            RentalTimesheetOvertime(
                company=company,
                period=period,
                worker=worker,
                assignment=assignment,
                hours=Decimal("10.00"),
                rate=Decimal("20.00"),
                supplier_code=supplier.code,
                supplier_name=supplier.name,
                project_code=project.code,
                project_name=project.name,
                trade=assignment.trade,
                rate_type=assignment.rate_type,
            )
        )
    RentalTimesheetEntry.objects.bulk_create(entries, batch_size=1000)
    RentalTimesheetOvertime.objects.bulk_create(overtime, batch_size=500)
    return supplier, project, period, workers


class SupplierTimesheetPackScaleProductionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="STP Scale Certification Company",
            legal_name="SESCCO",
            slug="stp-scale-certification",
        )
        cls.user = User.objects.create_user(
            username="stp-scale-owner",
            password="strong-password",
            email="owner@example.com",
        )
        cls.membership = CompanyMembership.objects.create(
            company=cls.company,
            user=cls.user,
            role=AccessRole.OWNER,
        )
        cls.supplier, cls.project, cls.period, cls.workers = _seed_pack_source(
            company=cls.company,
            user=cls.user,
            supplier_code="SUP-SCALE-250",
            worker_count=CERTIFIED_WORKERS,
        )

    def test_1_and_50_worker_sources_keep_the_same_two_query_budget(self):
        for worker_count, supplier_code in ((1, "SUP-SCALE-001"), (50, "SUP-SCALE-050")):
            supplier, _project, period, _workers = _seed_pack_source(
                company=self.company,
                user=self.user,
                supplier_code=supplier_code,
                worker_count=worker_count,
            )
            with self.assertNumQueries(2):
                snapshot = build_supplier_timesheet_pack_snapshot(
                    period,
                    supplier_code=supplier.code,
                )[0]
            self.assertEqual(snapshot["summary"]["worker_count"], worker_count)
            self.assertEqual(len(snapshot["workers"]), worker_count)
            self.assertTrue(all(len(worker["days"]) == 30 for worker in snapshot["workers"]))

    def test_250_worker_pack_uses_two_data_queries_and_stays_within_snapshot_budget(self):
        with self.assertNumQueries(2):
            snapshot = build_supplier_timesheet_pack_snapshot(
                self.period,
                supplier_code=self.supplier.code,
            )[0]
        self.assertEqual(snapshot["summary"]["worker_count"], CERTIFIED_WORKERS)
        self.assertEqual(len(snapshot["workers"]), CERTIFIED_WORKERS)
        self.assertTrue(all(len(worker["days"]) == 30 for worker in snapshot["workers"]))
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.assertLess(len(encoded), CERTIFIED_MAX_SNAPSHOT_BYTES)
        self.assertNotIn('"rate":', encoded.decode("utf-8").lower())

    def test_250_worker_full_print_and_worker_extract_are_query_free_and_reconcile(self):
        snapshot = build_supplier_timesheet_pack_snapshot(self.period, supplier_code=self.supplier.code)[0]
        with self.assertNumQueries(0):
            printable = build_supplier_timesheet_pack_print_context(snapshot)
        expected_summary_pages = (CERTIFIED_WORKERS + SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE - 1) // SUPPLIER_TIMESHEET_SUMMARY_ROWS_PER_PAGE
        self.assertEqual(printable["summary_page_count"], expected_summary_pages)
        self.assertEqual(printable["worker_page_count"], CERTIFIED_WORKERS)
        self.assertEqual(len(printable["worker_pages"]), CERTIFIED_WORKERS)

        with self.assertNumQueries(0):
            worker_context = build_supplier_timesheet_pack_worker_print_context(
                snapshot,
                worker_id=snapshot["workers"][137]["worker_id"],
            )
        self.assertTrue(worker_context["derived_from_pack"])
        self.assertEqual(len(worker_context["worker"]["days"]), 30)

    def test_finalization_is_retry_safe_and_keeps_one_immutable_pack(self):
        first = finalize_business_document(
            actor_membership=self.membership,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            source_id=self.period.pk,
            supplier_code=self.supplier.code,
            allow_supplier_timesheet_pack=True,
        )
        second = finalize_business_document(
            actor_membership=self.membership,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            source_id=self.period.pk,
            supplier_code=self.supplier.code,
            allow_supplier_timesheet_pack=True,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.snapshot_fingerprint, second.snapshot_fingerprint)
        self.assertEqual(
            BusinessDocument.objects.filter(
                company=self.company,
                document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
                source_id=self.period.pk,
            ).count(),
            1,
        )

    def test_scale_report_command_certifies_real_250_worker_locked_source(self):
        stdout = io.StringIO()
        call_command(
            "supplier_timesheet_pack_scale_report",
            "--company-slug",
            self.company.slug,
            "--period",
            "2026-06",
            "--project-code",
            self.project.code,
            "--supplier-code",
            self.supplier.code,
            "--min-workers",
            str(CERTIFIED_WORKERS),
            "--max-aggregate-queries",
            "2",
            "--max-print-queries",
            "0",
            "--max-snapshot-mib",
            "8",
            "--fail-on-limits",
            stdout=stdout,
        )
        report = stdout.getvalue()
        self.assertIn("250 workers", report)
        self.assertIn("2 queries", report)
        self.assertIn("Supplier Timesheet Pack scale limits passed", report)


class SupplierTimesheetPackConcurrentFinalizationTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Concurrent source-row locking certification is PostgreSQL-specific.")
        self.company = Company.objects.create(
            name="STP Concurrent Certification Company",
            legal_name="SESCCO",
            slug="stp-concurrent-certification",
        )
        self.user = User.objects.create_user(username="stp-concurrent-owner", password="strong-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.OWNER,
        )
        self.supplier, self.project, self.period, _workers = _seed_pack_source(
            company=self.company,
            user=self.user,
            supplier_code="SUP-CONCURRENT",
            worker_count=4,
        )

    def test_concurrent_pack_finalization_returns_one_document_without_integrity_error(self):
        barrier = threading.Barrier(2)
        document_ids: list[str] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def finalize() -> None:
            try:
                connections.close_all()
                membership = CompanyMembership.objects.select_related("company", "user").get(pk=self.membership.pk)
                barrier.wait(timeout=10)
                document = finalize_business_document(
                    actor_membership=membership,
                    document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
                    source_id=self.period.pk,
                    supplier_code=self.supplier.code,
                    allow_supplier_timesheet_pack=True,
                )
                with lock:
                    document_ids.append(str(document.pk))
            except BaseException as exc:  # pragma: no cover - asserted below with the real exception text
                with lock:
                    errors.append(exc)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=finalize, daemon=True) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        self.assertFalse(any(thread.is_alive() for thread in threads), "Concurrent finalization threads did not complete.")
        self.assertEqual(errors, [], [repr(error) for error in errors])
        self.assertEqual(len(document_ids), 2)
        self.assertEqual(len(set(document_ids)), 1)
        self.assertEqual(
            BusinessDocument.objects.filter(
                company=self.company,
                document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
                source_id=self.period.pk,
            ).count(),
            1,
        )
