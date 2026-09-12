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

        bad_open_projects = (
            WorkerAssignment.objects.filter(cancelled_at__isnull=True, effective_to__isnull=True)
            .filter(Q(project__status__in=[Project.Status.COMPLETED, Project.Status.ARCHIVED]) | Q(project__deleted_at__isnull=False))
            .count()
        )
        if bad_open_projects:
            errors.append(f"WorkerAssignment: {bad_open_projects} open assignments target completed/archived/trashed projects")

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
