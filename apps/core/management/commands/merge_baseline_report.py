from __future__ import annotations

import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.loader import MigrationLoader


BASELINE_MODELS = (
    "accounts.User",
    "accounts.CompanyMembership",
    "core.Company",
    "projects.Project",
    "inventory.Unit",
    "inventory.Supplier",
    "inventory.InventoryLocation",
    "inventory.StockItem",
    "inventory.StockDocument",
    "inventory.StockMovement",
    "inventory.StockTransfer",
    "inventory.StockTransferLine",
    "data_exchange.ImportJob",
    "data_exchange.ImportRow",
    "data_exchange.ExportAudit",
    "explorer.SavedView",
    "explorer.TablePreference",
)


class Command(BaseCommand):
    help = (
        "Emit a read-only IMS pre-merge data/migration baseline. Run this against a production "
        "backup before tenant/payroll schema migrations."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=Path,
            help="Optional path for a JSON copy of the report.",
        )
        parser.add_argument(
            "--indent",
            type=int,
            default=2,
            help="JSON indentation (default: 2).",
        )

    def handle(self, *args, **options):
        counts: dict[str, int | None] = {}
        for label in BASELINE_MODELS:
            try:
                model = apps.get_model(label)
                counts[label] = model._default_manager.count()
            except Exception as exc:  # pragma: no cover - defensive report path
                counts[label] = None
                self.stderr.write(f"Could not count {label}: {exc}")

        loader = MigrationLoader(connection, ignore_no_migrations=True)
        leaf_nodes = sorted(f"{app}.{name}" for app, name in loader.graph.leaf_nodes())

        report = {
            "app_name": getattr(settings, "APP_NAME", "IMS"),
            "app_version": getattr(settings, "APP_VERSION", "unknown"),
            "database_vendor": connection.vendor,
            "auth_user_model": settings.AUTH_USER_MODEL,
            "model_counts": counts,
            "migration_leaf_nodes": leaf_nodes,
        }
        payload = json.dumps(report, indent=options["indent"], sort_keys=True, default=str)
        self.stdout.write(payload)

        output = options.get("output")
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
            self.stderr.write(self.style.SUCCESS(f"Baseline report written to {output}"))
