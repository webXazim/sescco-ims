from __future__ import annotations

import json

from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q

from apps.core.models import Company
from apps.projects.models import Project


class Command(BaseCommand):
    help = "Emit a read-only post-Upgrade-5 canonical shared-project reconciliation report."

    def add_arguments(self, parser):
        parser.add_argument("--indent", type=int, default=2)
        parser.add_argument(
            "--fail-on-errors",
            action="store_true",
            help="Exit non-zero when the canonical project authority has invalid identity or tenant data.",
        )

    def handle(self, *args, **options):
        errors: dict[str, int] = {}
        warnings: dict[str, int] = {}

        def check(target: dict[str, int], name: str, queryset) -> None:
            count = queryset.count()
            if count:
                target[name] = count

        check(errors, "project_without_company", Project.objects.filter(company__isnull=True))
        check(errors, "project_without_reference", Project.objects.filter(reference__isnull=True))
        check(
            errors,
            "duplicate_company_code",
            Project.objects.values("company_id", "code")
            .annotate(total=Count("pk"))
            .filter(total__gt=1),
        )
        check(
            errors,
            "duplicate_public_reference",
            Project.objects.values("reference").annotate(total=Count("pk")).filter(total__gt=1),
        )
        check(
            errors,
            "project_end_before_start",
            Project.objects.filter(start_date__isnull=False, end_date__isnull=False, end_date__lt=F("start_date")),
        )
        check(
            errors,
            "unknown_project_status",
            Project.objects.exclude(status__in=Project.Status.values),
        )
        # Legacy Inventory projects may already have been completed before Upgrade 5 without an
        # actual end date. We do not fabricate historical dates; flag them for business review.
        check(
            warnings,
            "legacy_completed_without_end_date",
            Project.objects.filter(status=Project.Status.COMPLETED, end_date__isnull=True),
        )

        per_company = {}
        for company in Company.objects.order_by("name", "id"):
            projects = Project.objects.filter(company=company)
            per_company[str(company.pk)] = {
                "name": company.name,
                "projects": projects.count(),
                "active": projects.filter(status=Project.Status.ACTIVE, deleted_at__isnull=True).count(),
                "on_hold": projects.filter(status=Project.Status.ON_HOLD, deleted_at__isnull=True).count(),
                "completed": projects.filter(status=Project.Status.COMPLETED, deleted_at__isnull=True).count(),
                "archived": projects.filter(status=Project.Status.ARCHIVED, deleted_at__isnull=True).count(),
                "with_start_date": projects.filter(start_date__isnull=False).count(),
                "with_actual_end_date": projects.filter(end_date__isnull=False).count(),
                "with_manager": projects.exclude(manager_name="").count(),
            }

        report = {
            "authority": "projects.Project",
            "public_identity": "reference UUID",
            "database_identity": "existing integer primary key",
            "projects": Project.objects.count(),
            "companies": Company.objects.count(),
            "per_company": per_company,
            "warnings": warnings,
            "errors": errors,
        }
        self.stdout.write(json.dumps(report, indent=options["indent"], sort_keys=True))

        if options["fail_on_errors"] and errors:
            self.stderr.write(self.style.ERROR("Shared-project reconciliation failed."))
            raise SystemExit(2)
