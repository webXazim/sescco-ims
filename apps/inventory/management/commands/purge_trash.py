from django.core.management.base import BaseCommand
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.inventory.models import StockItem, Supplier, Unit
from apps.projects.models import Project


class Command(BaseCommand):
    help = "Permanently remove expired Trash records when audit relationships allow it."

    def handle(self, *args, **options):
        now = timezone.now()
        deleted = 0
        protected = 0
        for model in (StockItem, Supplier, Unit, Project):
            for instance in model.objects.filter(deleted_at__isnull=False, purge_after__lte=now):
                try:
                    instance.delete()
                    deleted += 1
                except ProtectedError:
                    # Immutable movements/import evidence must retain its relational tombstone.
                    model.objects.filter(pk=instance.pk).update(
                        deletion_reason="", deleted_by=None
                    )
                    protected += 1
        self.stdout.write(self.style.SUCCESS(
            f"Purged {deleted} expired records; retained {protected} protected audit tombstones."
        ))
