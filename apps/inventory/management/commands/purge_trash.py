from django.core.management.base import BaseCommand
from django.db import router
from django.db.models.deletion import Collector, ProtectedError, RestrictedError
from django.utils import timezone

from apps.internal_payroll.models import Branch, Department, InternalEmployee
from apps.inventory.models import InventoryLocation, StockItem, Supplier, Unit
from apps.projects.models import Project
from apps.rental_manpower.models import ManpowerSupplier, RentalWorker


def _hard_delete_is_history_safe(instance) -> bool:
    """Return True only when deleting *instance* cannot delete any related row.

    Trash expiry must never turn a soft-delete into a cascading historical-data
    deletion.  Django's deletion Collector gives us the exact cascade plan.  We
    permit a physical delete only when the collector contains the root object
    and nothing else, with no fast-delete querysets queued.  PROTECT/RESTRICT
    relationships are also treated as retained tombstones.
    """

    using = router.db_for_write(instance.__class__, instance=instance)
    collector = Collector(using=using, origin=instance)
    try:
        collector.collect([instance])
    except (ProtectedError, RestrictedError):
        return False

    if collector.fast_deletes:
        return False

    for model, objects in collector.data.items():
        for obj in objects:
            if model is not instance.__class__ or obj.pk != instance.pk:
                return False
    return True


class Command(BaseCommand):
    help = "Permanently remove expired Trash records only when no related history can be deleted."

    def handle(self, *args, **options):
        now = timezone.now()
        deleted = 0
        retained = 0
        models = (
            StockItem,
            Supplier,
            Unit,
            InventoryLocation,
            Project,
            Branch,
            Department,
            InternalEmployee,
            ManpowerSupplier,
            RentalWorker,
        )

        for model in models:
            for instance in model.objects.filter(deleted_at__isnull=False, purge_after__lte=now):
                if not _hard_delete_is_history_safe(instance):
                    # The 30-day recovery window is over, so this master stops
                    # appearing in Trash.  Keep the hidden tombstone itself so
                    # existing payroll/inventory/assignment/audit relations can
                    # continue to resolve without any cascading data loss.
                    model.objects.filter(pk=instance.pk).update(purge_after=None)
                    retained += 1
                    continue
                try:
                    instance.delete()
                    deleted += 1
                except (ProtectedError, RestrictedError):
                    # Defensive race/concurrency fallback: if a protected
                    # relationship appeared after collection, retain the same
                    # hidden historical tombstone rather than retrying forever.
                    model.objects.filter(pk=instance.pk).update(purge_after=None)
                    retained += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {deleted} expired records; retained {retained} protected historical tombstones."
            )
        )
