from __future__ import annotations

import io
from datetime import date
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company, CompanySettings
from apps.documents.models import BusinessDocument, DocumentType
from apps.documents.services.documents import SUPPLIER_TIMESHEET_ALIAS, finalize_business_document
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


class SupplierTimesheetPackProductionFreezeAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.company = Company.objects.create(
            name="STP Final Acceptance Company",
            legal_name="SESCCO",
            slug="stp-final-acceptance",
        )
        CompanySettings.objects.get_or_create(company=cls.company)
        cls.user = User.objects.create_user(
            username="stp-final-owner",
            password="strong-password",
            email="owner@example.com",
        )
        cls.membership = CompanyMembership.objects.create(
            company=cls.company,
            user=cls.user,
            role=AccessRole.OWNER,
        )
        cls.supplier = ManpowerSupplier.objects.create(
            company=cls.company,
            code="SUP-FINAL",
            name="Final Acceptance Supplier",
            contact_person="Supplier Accounts",
            email="supplier-final@example.com",
        )
        cls.project = Project.objects.create(
            company=cls.company,
            code="PRJ-FINAL",
            name="Final Acceptance Project",
            start_date=date(2026, 6, 1),
            created_by=cls.user,
            updated_by=cls.user,
        )
        cls.period = RentalTimesheetPeriod.objects.create(
            company=cls.company,
            project=cls.project,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
            status=RentalTimesheetStatus.LOCKED,
            revision=7,
            locked_at=timezone.now(),
            locked_by=cls.user,
        )
        cls.worker = RentalWorker.objects.create(
            company=cls.company,
            worker_number="RW-FINAL-001",
            full_name="Final Acceptance Worker",
            supplier=cls.supplier,
        )
        cls.assignment = WorkerAssignment.objects.create(
            company=cls.company,
            worker=cls.worker,
            project=cls.project,
            trade="Mason",
            rate_type=RentalRateType.HOURLY,
            rate=Decimal("15.00"),
            effective_from=date(2026, 6, 1),
            reason="Supplier Timesheet Pack final acceptance",
        )
        RentalTimesheetEntry.objects.bulk_create(
            [
                RentalTimesheetEntry(
                    company=cls.company,
                    period=cls.period,
                    worker=cls.worker,
                    assignment=cls.assignment,
                    work_date=date(2026, 6, day),
                    regular_hours=Decimal("8.00"),
                    code="",
                    note="",
                    supplier_code=cls.supplier.code,
                    supplier_name=cls.supplier.name,
                    project_code=cls.project.code,
                    project_name=cls.project.name,
                    trade=cls.assignment.trade,
                    rate_type=cls.assignment.rate_type,
                    rate=cls.assignment.rate,
                )
                for day in range(1, 31)
            ]
        )
        RentalTimesheetOvertime.objects.create(
            company=cls.company,
            period=cls.period,
            worker=cls.worker,
            assignment=cls.assignment,
            hours=Decimal("10.00"),
            rate=Decimal("20.00"),
            supplier_code=cls.supplier.code,
            supplier_name=cls.supplier.name,
            project_code=cls.project.code,
            project_name=cls.project.name,
            trade=cls.assignment.trade,
            rate_type=cls.assignment.rate_type,
        )

    def _finalize_v3(self):
        return finalize_business_document(
            actor_membership=self.membership,
            document_type=DocumentType.SUPPLIER_TIMESHEET_PACK,
            source_id=self.period.pk,
            supplier_code=self.supplier.code,
            allow_supplier_timesheet_pack=True,
        )

    def test_management_reconciliation_accepts_legacy_and_v3_supplier_timesheet_sources(self):
        legacy = finalize_business_document(
            actor_membership=self.membership,
            document_type=SUPPLIER_TIMESHEET_ALIAS,
            source_id=self.period.pk,
            supplier_code=self.supplier.code,
        )
        pack = self._finalize_v3()

        self.assertEqual(legacy.document_type, DocumentType.RENTAL_TIMESHEET)
        self.assertEqual(pack.document_type, DocumentType.SUPPLIER_TIMESHEET_PACK)
        self.assertEqual(legacy.source_model, "rental_manpower.rentaltimesheetperiod:supplier:SUP-FINAL")
        self.assertEqual(pack.source_model, legacy.source_model)

        stdout = io.StringIO()
        call_command("merge_documents_management_report", "--fail-on-errors", stdout=stdout)
        self.assertIn("Documents, settings and audit ownership are valid.", stdout.getvalue())

    def test_management_reconciliation_verifies_v3_snapshot_source_binding(self):
        pack = self._finalize_v3()
        self.assertEqual(pack.snapshot["source"]["id"], str(self.period.pk))
        self.assertEqual(pack.snapshot["source"]["revision"], self.period.revision)
        self.assertEqual(pack.snapshot["supplier"]["code"], self.supplier.code)
        self.assertEqual(pack.entity_reference, self.supplier.code)
        self.assertTrue(pack.document_number.startswith("STP-"))

        call_command("merge_documents_management_report", "--fail-on-errors", stdout=io.StringIO())

    def test_management_reconciliation_fails_closed_on_v3_source_fingerprint_drift(self):
        pack = self._finalize_v3()
        table = connection.ops.quote_name(BusinessDocument._meta.db_table)
        document_pk = pack.pk.hex if connection.vendor == "sqlite" else str(pack.pk)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET source_fingerprint = %s WHERE id = %s",
                ["0" * 64, document_pk],
            )

        with self.assertRaises(CommandError):
            call_command(
                "merge_documents_management_report",
                "--fail-on-errors",
                stdout=io.StringIO(),
                stderr=io.StringIO(),
            )
