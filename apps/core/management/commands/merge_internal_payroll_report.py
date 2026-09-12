from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F

from apps.internal_payroll import models as payroll_models


class Command(BaseCommand):
    help = "Reconcile Internal Payroll tenant integrity after the IMS + Payroll merge."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-errors", action="store_true")

    def handle(self, *args, **options):
        model_names = list(payroll_models.__all__)
        model_classes = []
        seen = set()
        for name in model_names:
            candidate = getattr(payroll_models, name, None)
            meta = getattr(candidate, "_meta", None)
            if meta is None or meta.abstract or meta.proxy:
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            model_classes.append(candidate)

        errors: list[str] = []
        total_rows = 0
        self.stdout.write("Internal Payroll merge reconciliation")
        for model in sorted(model_classes, key=lambda item: item._meta.label_lower):
            company_field = next((field for field in model._meta.fields if field.name == "company"), None)
            if company_field is None:
                errors.append(f"{model._meta.label}: missing direct company ownership")
                continue

            count = model.objects.count()
            total_rows += count
            self.stdout.write(f"  {model._meta.label}: {count}")

            null_company = model.objects.filter(company_id__isnull=True).count()
            if null_company:
                errors.append(f"{model._meta.label}: {null_company} rows have no company")

            # Every FK to another company-owned model must remain inside the row's company.
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
                    errors.append(
                        f"{model._meta.label}.{field.name}: {mismatch} cross-company references"
                    )

        self.stdout.write(f"Total Internal Payroll rows: {total_rows}")
        if errors:
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
            if options["fail_on_errors"]:
                raise CommandError(f"Internal Payroll reconciliation failed with {len(errors)} error(s).")
            return
        self.stdout.write(self.style.SUCCESS("Internal Payroll tenant integrity is valid."))
