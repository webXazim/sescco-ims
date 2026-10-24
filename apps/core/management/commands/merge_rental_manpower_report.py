from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q


class Command(BaseCommand):
    help = "Reconcile Rental Manpower tenant/shared-project integrity after the IMS + Payroll merge."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-errors", action="store_true")

    def handle(self, *args, **options):
        config = django_apps.get_app_config("rental_manpower")
        models = list(config.get_models())
        errors: list[str] = []
        warnings: list[str] = []
        total_rows = 0

        self.stdout.write("Rental Manpower merge reconciliation")
        if any(model.__name__ == "RentalProject" for model in models):
            errors.append("A duplicate rental_manpower.RentalProject model is installed")

        for model in sorted(models, key=lambda item: item._meta.label_lower):
            field_names = {field.name for field in model._meta.fields}
            if "company" not in field_names:
                errors.append(f"{model._meta.label}: missing direct company ownership")
                continue

            count = model.objects.count()
            total_rows += count
            self.stdout.write(f"  {model._meta.label}: {count}")

            null_company = model.objects.filter(company_id__isnull=True).count()
            if null_company:
                errors.append(f"{model._meta.label}: {null_company} rows have no company")

            for field in model._meta.fields:
                if not field.is_relation or field.many_to_many or not field.remote_field:
                    continue
                related = field.remote_field.model
                related_meta = getattr(related, "_meta", None)
                if related_meta is None:
                    continue
                related_fields = {item.name for item in related_meta.fields}
                if "company" not in related_fields:
                    continue
                # Nullable company-owned relations are valid when unset.  Compare tenant
                # ownership only for rows that actually reference a related object; using
                # exclude() directly on a nullable FK makes Django include NULL relations
                # in the negated predicate and produces a false cross-company error.
                relation_scope = model.objects.filter(**{f"{field.name}__isnull": False})
                mismatch = relation_scope.exclude(**{f"{field.name}__company_id": F("company_id")}).count()
                if mismatch:
                    errors.append(f"{model._meta.label}.{field.name}: {mismatch} cross-company references")

        Project = django_apps.get_model("projects", "Project")
        WorkerAssignment = django_apps.get_model("rental_manpower", "WorkerAssignment")
        RentalWorker = django_apps.get_model("rental_manpower", "RentalWorker")

        # Project Archive and Trash are reversible visibility boundaries, not
        # assignment releases. Their lifecycle policies intentionally retain rental
        # assignments and timesheet history so restoration is lossless. Do not treat
        # those retained open segments as a tenant/integrity failure.
        open_assignments = WorkerAssignment.objects.filter(
            cancelled_at__isnull=True, effective_to__isnull=True
        )
        hidden_project_assignments = open_assignments.filter(
            Q(project__status=Project.Status.ARCHIVED)
            | Q(project__archived_at__isnull=False)
            | Q(project__deleted_at__isnull=False)
        ).count()
        if hidden_project_assignments:
            self.stdout.write(
                "  WorkerAssignment: "
                f"{hidden_project_assignments} open assignment(s) preserved on archived/trashed projects "
                "(valid reversible lifecycle state)"
            )

        # Completing a visible project is different: Project.clean() requires
        # release/transfer of its open rental assignments first. Keep a hard error
        # for invalid historical rows, but never silently rewrite assignment dates.
        completed_open = open_assignments.filter(
            project__status=Project.Status.COMPLETED,
            project__archived_at__isnull=True,
            project__deleted_at__isnull=True,
        )
        bad_completed_count = completed_open.count()
        if bad_completed_count:
            sample_codes = list(
                completed_open.order_by().values_list("project__code", flat=True).distinct()[:5]
            )
            errors.append(
                f"WorkerAssignment: {bad_completed_count} open assignments target completed projects "
                f"(project codes: {', '.join(sample_codes)}). "
                "Review timesheets, then release/transfer affected workers; no records were modified."
            )

        bad_open_workers = WorkerAssignment.objects.filter(
            cancelled_at__isnull=True,
            effective_to__isnull=True,
            worker__status="inactive",
        ).count()
        if bad_open_workers:
            warnings.append(f"WorkerAssignment: {bad_open_workers} open assignments belong to inactive worker masters")

        workers_cross_supplier = RentalWorker.objects.exclude(supplier__company_id=F("company_id")).count()
        if workers_cross_supplier:
            errors.append(f"RentalWorker.supplier: {workers_cross_supplier} cross-company references")

        self.stdout.write(f"Total Rental Manpower rows: {total_rows}")
        for warning in warnings:
            self.stderr.write(self.style.WARNING(f"WARNING: {warning}"))
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_errors"]:
                raise CommandError(f"Rental Manpower reconciliation failed with {len(errors)} error(s).")
            return
        self.stdout.write(self.style.SUCCESS("Rental Manpower tenant and shared-project integrity is valid."))
