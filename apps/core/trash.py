from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

TRASH_RETENTION_DAYS = 30


def move_to_trash(instance, *, user, reason: str) -> None:
    now = timezone.now()
    instance.deleted_at = now
    instance.deleted_by = user
    instance.deletion_reason = reason.strip()
    instance.purge_after = now + timedelta(days=TRASH_RETENTION_DAYS)
    instance.updated_at = now
    instance.save(
        update_fields=("deleted_at", "deleted_by", "deletion_reason", "purge_after", "updated_at")
    )


def restore_from_trash(instance) -> bool:
    if (
        not instance.deleted_at
        or not instance.purge_after
        or instance.purge_after <= timezone.now()
    ):
        return False
    instance.deleted_at = None
    instance.deleted_by = None
    instance.deletion_reason = ""
    instance.purge_after = None
    instance.updated_at = timezone.now()
    instance.save(
        update_fields=("deleted_at", "deleted_by", "deletion_reason", "purge_after", "updated_at")
    )
    return True


def active_trash(queryset):
    return queryset.filter(deleted_at__isnull=False, purge_after__gt=timezone.now())
