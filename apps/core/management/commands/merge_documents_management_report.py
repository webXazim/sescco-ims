from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError

from apps.documents.services import verify_document_snapshot


class Command(BaseCommand):
    help = "Reconcile Payroll Documents, Company Settings and audit ownership after the merged-platform import."

    def add_arguments(self, parser):
        parser.add_argument("--fail-on-errors", action="store_true")

    def handle(self, *args, **options):
        Company = django_apps.get_model("core", "Company")
        CompanySettings = django_apps.get_model("core", "CompanySettings")
        AuditEvent = django_apps.get_model("core", "AuditEvent")
        CompanyMembership = django_apps.get_model("accounts", "CompanyMembership")
        BusinessDocument = django_apps.get_model("documents", "BusinessDocument")

        errors: list[str] = []
        warnings: list[str] = []

        self.stdout.write("Documents / Management merge reconciliation")
        company_count = Company.objects.count()
        document_count = BusinessDocument.objects.count()
        audit_count = AuditEvent.objects.count()
        self.stdout.write(f"  companies: {company_count}")
        self.stdout.write(f"  business documents: {document_count}")
        self.stdout.write(f"  audit events: {audit_count}")

        missing_settings = Company.objects.exclude(pk__in=CompanySettings.objects.values("company_id")).count()
        if missing_settings:
            errors.append(f"CompanySettings: {missing_settings} companies are missing settings")

        for document in BusinessDocument.objects.select_related("company").iterator():
            if not verify_document_snapshot(document):
                errors.append(f"BusinessDocument {document.pk}: snapshot fingerprint mismatch")
                continue
            try:
                app_label, model_name = document.source_model.split(".", 1)
                source_model = django_apps.get_model(app_label, model_name)
            except (ValueError, LookupError):
                errors.append(f"BusinessDocument {document.pk}: unknown source model {document.source_model!r}")
                continue
            source_company_id = source_model.objects.filter(pk=document.source_id).values_list("company_id", flat=True).first()
            if source_company_id is None:
                errors.append(
                    f"BusinessDocument {document.pk}: missing source {document.source_model}:{document.source_id}"
                )
                continue
            if source_company_id != document.company_id:
                errors.append(f"BusinessDocument {document.pk}: source belongs to a different company")

        membership_by_id = {
            str(row.id): row.company_id
            for row in CompanyMembership.objects.only("id", "company_id").iterator()
        }
        for event in AuditEvent.objects.exclude(actor_membership_id__isnull=True).only(
            "id", "company_id", "actor_membership_id"
        ).iterator():
            membership_company = membership_by_id.get(str(event.actor_membership_id))
            if membership_company is None:
                warnings.append(f"AuditEvent {event.pk}: actor membership no longer exists")
            elif membership_company != event.company_id:
                errors.append(f"AuditEvent {event.pk}: actor membership belongs to a different company")

        for warning in warnings[:100]:
            self.stderr.write(self.style.WARNING(f"WARNING: {warning}"))
        if len(warnings) > 100:
            self.stderr.write(self.style.WARNING(f"WARNING: {len(warnings) - 100} additional warnings omitted"))

        if errors:
            for error in errors[:100]:
                self.stderr.write(self.style.ERROR(error))
            if len(errors) > 100:
                self.stderr.write(self.style.ERROR(f"{len(errors) - 100} additional errors omitted"))
            if options["fail_on_errors"]:
                raise CommandError(f"Documents / Management reconciliation failed with {len(errors)} error(s).")
            return

        self.stdout.write(self.style.SUCCESS("Documents, settings and audit ownership are valid."))
