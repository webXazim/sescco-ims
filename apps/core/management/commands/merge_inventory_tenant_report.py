from __future__ import annotations

import json
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from apps.accounts.models import CompanyMembership
from apps.core.models import Company
from apps.data_exchange.models import ExportAudit, ImportJob
from apps.explorer.models import SavedView, TablePreference
from apps.inventory.models import (
    InventoryLocation,
    StockDocument,
    StockItem,
    StockMovement,
    StockTransfer,
    StockTransferLine,
    Supplier,
    Unit,
)
from apps.projects.models import Project


TENANT_MODELS = (
    ("projects", Project),
    ("units", Unit),
    ("material_suppliers", Supplier),
    ("locations", InventoryLocation),
    ("stock_items", StockItem),
    ("stock_documents", StockDocument),
    ("stock_movements", StockMovement),
    ("stock_transfers", StockTransfer),
    ("import_jobs", ImportJob),
    ("export_audits", ExportAudit),
    ("saved_views", SavedView),
    ("table_preferences", TablePreference),
)


class Command(BaseCommand):
    help = "Emit a read-only post-Upgrade-4 Inventory tenant-boundary reconciliation report."

    def add_arguments(self, parser):
        parser.add_argument("--indent", type=int, default=2)
        parser.add_argument(
            "--fail-on-errors",
            action="store_true",
            help="Exit non-zero when any Inventory relation crosses a company boundary.",
        )

    def handle(self, *args, **options):
        errors: dict[str, int] = {}

        def check(name: str, queryset) -> None:
            count = queryset.count()
            if count:
                errors[name] = count

        check(
            "location_project_company_mismatch",
            InventoryLocation.objects.filter(project__isnull=False).exclude(company_id=F("project__company_id")),
        )
        check(
            "stock_location_company_mismatch",
            StockItem.objects.exclude(company_id=F("location__company_id")),
        )
        check(
            "stock_project_company_mismatch",
            StockItem.objects.filter(project__isnull=False).exclude(company_id=F("project__company_id")),
        )
        check(
            "stock_unit_company_mismatch",
            StockItem.objects.exclude(company_id=F("unit__company_id")),
        )
        check(
            "document_stock_company_mismatch",
            StockDocument.objects.exclude(company_id=F("stock_item__company_id")),
        )
        check(
            "movement_stock_company_mismatch",
            StockMovement.objects.exclude(company_id=F("stock_item__company_id")),
        )
        check(
            "movement_reversal_company_mismatch",
            StockMovement.objects.filter(reversal_of__isnull=False).exclude(
                company_id=F("reversal_of__company_id")
            ),
        )
        check(
            "transfer_source_company_mismatch",
            StockTransfer.objects.exclude(company_id=F("source_location__company_id")),
        )
        check(
            "transfer_destination_company_mismatch",
            StockTransfer.objects.exclude(company_id=F("destination_location__company_id")),
        )
        check(
            "transfer_line_source_company_mismatch",
            StockTransferLine.objects.exclude(
                transfer__company_id=F("source_stock_item__company_id")
            ),
        )
        check(
            "transfer_line_destination_company_mismatch",
            StockTransferLine.objects.filter(destination_stock_item__isnull=False).exclude(
                transfer__company_id=F("destination_stock_item__company_id")
            ),
        )
        check(
            "transfer_line_source_location_mismatch",
            StockTransferLine.objects.exclude(
                transfer__source_location_id=F("source_stock_item__location_id")
            ),
        )
        check(
            "transfer_line_destination_location_mismatch",
            StockTransferLine.objects.filter(destination_stock_item__isnull=False).exclude(
                transfer__destination_location_id=F("destination_stock_item__location_id")
            ),
        )
        check(
            "movement_transfer_line_company_mismatch",
            StockMovement.objects.filter(transfer_line__isnull=False).exclude(
                company_id=F("transfer_line__transfer__company_id")
            ),
        )
        check(
            "import_project_company_mismatch",
            ImportJob.objects.filter(project__isnull=False).exclude(company_id=F("project__company_id")),
        )
        check(
            "import_unit_company_mismatch",
            ImportJob.objects.filter(default_unit__isnull=False).exclude(
                company_id=F("default_unit__company_id")
            ),
        )
        check(
            "saved_view_owner_without_company_membership",
            SavedView.objects.exclude(
                Q(owner__company_memberships__company_id=F("company_id"))
                & Q(owner__company_memberships__is_active=True)
            ),
        )
        check(
            "table_preference_owner_without_company_membership",
            TablePreference.objects.exclude(
                Q(owner__company_memberships__company_id=F("company_id"))
                & Q(owner__company_memberships__is_active=True)
            ),
        )

        per_company: dict[str, dict[str, object]] = {}
        companies = Company.objects.order_by("name", "id")
        for company in companies:
            counts = {
                label: model.objects.filter(company=company).count()
                for label, model in TENANT_MODELS
            }
            counts["active_memberships"] = CompanyMembership.objects.filter(
                company=company,
                is_active=True,
                user__is_active=True,
            ).count()
            per_company[str(company.pk)] = {
                "name": company.name,
                "active": company.is_active,
                "counts": counts,
            }

        report = {
            "companies": companies.count(),
            "tenant_models": {
                label: model.objects.count() for label, model in TENANT_MODELS
            },
            "per_company": per_company,
            "boundary_errors": errors,
        }
        self.stdout.write(json.dumps(report, indent=options["indent"], sort_keys=True))

        if options["fail_on_errors"] and errors:
            self.stderr.write(self.style.ERROR("Inventory tenant-boundary reconciliation failed."))
            raise SystemExit(2)
