"""History-safe irreversible dismissal of recoverable Trash entries.

A record that has references is retained as a hidden tombstone. No operation here
may cascade into operational, payroll, stock movement or audit history.
"""
from __future__ import annotations

from django.apps import apps as django_apps
from django.db import IntegrityError, router, transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError

from apps.core.models import TrashCascadeLink
from apps.core.trash import release_cascade_child_ownership


def _hard_delete_is_history_safe(instance) -> bool:
    """Return True only when deleting *instance* cannot delete any related row.

    Trash expiry must never turn a soft-delete into a cascading historical-data
    deletion.  Django's deletion Collector gives us the exact cascade plan.  We
    permit a physical delete only when the collector contains the root object
    and nothing else, with no fast-delete querysets queued.  PROTECT/RESTRICT
    relationships are also treated as retained tombstones.
    """

    # An active balance cannot be physically discarded at Trash expiry even
    # if legacy/imported data lacks a movement row. Keep a hidden tombstone.
    if isinstance(instance, StockItem) and instance.current_quantity:
        return False

    using = router.db_for_write(instance.__class__, instance=instance)
    collector = Collector(using=using, origin=instance)
    try:
        collector.collect([instance])
    except (ProtectedError, RestrictedError):
        return False

    if collector.fast_deletes or collector.field_updates:
        # SET_NULL (and similar collector updates) would rewrite surviving
        # reference rows, even without deleting them. Keep a tombstone instead.
        return False

    for model, objects in collector.data.items():
        for obj in objects:
            if model is not instance.__class__ or obj.pk != instance.pk:
                return False
    return True



def dismiss_trash_entry(instance):
    """End recoverability. Return 'deleted' or 'retained' (protected history)."""
    if not instance.deleted_at or not instance.purge_after:
        raise ValueError("Only recoverable Trash entries can be dismissed.")

    # A project Trash action may own stock and location children which are not
    # displayed as independent Trash entries. End that exact cascade window too.
    root_type = f"{instance._meta.app_label}.{instance._meta.object_name}"
    links = list(TrashCascadeLink.objects.select_for_update().filter(
        company=instance.company, root_type=root_type, root_id=str(instance.pk),
        restored_at__isnull=True,
    ))
    for link in links:
        try:
            app_label, model_name = link.child_type.split(".", 1)
            model = django_apps.get_model(app_label, model_name)
        except (ValueError, LookupError):
            raise ValueError("Unknown cascade child type; the record was not removed.")
        child = model.objects.select_for_update().filter(
            company=instance.company, pk=link.child_id
        ).first()
        if child and child.deleted_at == instance.deleted_at and child.purge_after == instance.purge_after:
            dismiss_trash_entry(child)
        # Links to independently restored/re-deleted children are retired, not acted on.
        if TrashCascadeLink.objects.filter(pk=link.pk, restored_at__isnull=True).exists():
            release_cascade_child_ownership_by_id(link.pk)

    release_cascade_child_ownership(instance)
    if not _hard_delete_is_history_safe(instance):
        type(instance).objects.filter(pk=instance.pk).update(purge_after=None)
        return "retained"
    # The savepoint prevents a rare FK race from aborting the whole transaction.
    try:
        with transaction.atomic():
            instance.delete()
        return "deleted"
    except (ProtectedError, RestrictedError, IntegrityError):
        type(instance).objects.filter(pk=instance.pk).update(purge_after=None)
        return "retained"


def release_cascade_child_ownership_by_id(pk):
    from django.utils import timezone
    TrashCascadeLink.objects.filter(pk=pk, restored_at__isnull=True).update(
        restored_at=timezone.now(), updated_at=timezone.now()
    )
