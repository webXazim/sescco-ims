from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from django.apps import apps as django_apps
from django.core.exceptions import ValidationError
from django.utils import timezone

TRASH_RETENTION_DAYS = 30


def _model_label(instance) -> str:
    return f"{instance._meta.app_label}.{instance._meta.object_name}"


def move_to_trash(instance, *, user, reason: str, deleted_at=None, purge_after=None) -> None:
    """Move one lifecycle-managed master into the recoverable Trash window.

    ``deleted_at``/``purge_after`` are optional so a parent cascade can put every
    child in the exact same 30-day recovery window as its root record.
    """

    now = deleted_at or timezone.now()
    instance.deleted_at = now
    instance.deleted_by = user
    instance.deletion_reason = reason.strip()
    instance.purge_after = purge_after or (now + timedelta(days=TRASH_RETENTION_DAYS))
    instance.updated_at = now
    instance.save(
        update_fields=("deleted_at", "deleted_by", "deletion_reason", "purge_after", "updated_at")
    )


def release_cascade_child_ownership(instance) -> int:
    """Retire any parent-cascade ownership when a child leaves that Trash state.

    A cascade link describes one exact recoverable delete event, not permanent
    ownership of the child master.  Independent child restore, expiry/purge or a
    later independent delete must therefore never remain attached to the stale
    parent action.
    """

    from apps.core.models import TrashCascadeLink

    now = timezone.now()
    return (
        TrashCascadeLink.objects.for_company(instance.company)
        .filter(
            child_type=_model_label(instance),
            child_id=str(instance.pk),
            restored_at__isnull=True,
        )
        .update(restored_at=now, updated_at=now)
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
    release_cascade_child_ownership(instance)
    return True


def cascade_to_trash(*, root, children: Iterable, user, reason: str) -> int:
    """Soft-delete currently active child masters and remember exact ownership.

    A child already in Trash is intentionally skipped. This prevents restoring a
    parent from accidentally resurrecting a child that was independently deleted
    before the parent action.
    """

    from apps.core.models import TrashCascadeLink

    root_type = _model_label(root)
    root_id = str(root.pk)
    count = 0
    for child in children:
        if getattr(child, "deleted_at", None):
            continue
        child_type = _model_label(child)
        child_id = str(child.pk)
        existing = TrashCascadeLink.objects.filter(
            company=root.company, root_type=root_type, root_id=root_id,
            child_type=child_type, child_id=child_id, restored_at__isnull=True,
        ).exists()
        if existing:
            continue
        TrashCascadeLink.objects.create(
            company=root.company, root_type=root_type, root_id=root_id,
            child_type=child_type, child_id=child_id, deleted_by=user,
            reason=(reason or "").strip(),
        )
        move_to_trash(
            child,
            user=user,
            reason=f"Cascade from {root_type} {root_id}: {(reason or '').strip()}".strip(),
            deleted_at=root.deleted_at,
            purge_after=root.purge_after,
        )
        count += 1
    return count


def restore_trash_cascade(*, root, deleted_at, purge_after) -> int:
    """Restore exactly the child masters deleted by ``root`` during its Trash action.

    ``deleted_at``/``purge_after`` are the root's Trash window captured before
    the root itself is restored. Matching those values is mandatory: a stale
    cascade link can never resurrect a child from a newer independent delete.
    """

    if deleted_at is None or purge_after is None:
        raise ValidationError({"record": "The parent Trash recovery window is required for cascade restore."})

    from apps.core.models import TrashCascadeLink

    root_type = _model_label(root)
    links = list(
        TrashCascadeLink.objects.select_for_update()
        .for_company(root.company)
        .filter(root_type=root_type, root_id=str(root.pk), restored_at__isnull=True)
        .order_by("created_at", "id")
    )
    if not links:
        return 0

    now = timezone.now()
    resolved = []
    for link in links:
        try:
            app_label, model_name = link.child_type.split(".", 1)
            model = django_apps.get_model(app_label, model_name)
        except (ValueError, LookupError) as exc:
            raise ValidationError({"record": "A cascaded Trash child type can no longer be resolved."}) from exc
        child = model.objects.select_for_update().filter(pk=link.child_id, company=root.company).first()
        if child is None:
            # Already physically purged with an expired parent; nothing can be restored.
            raise ValidationError({"record": "A cascaded Trash child has already been permanently removed."})
        should_restore = bool(child.deleted_at)
        if child.deleted_at:
            # A child can be independently restored while its parent stays in
            # Trash.  If it is deleted again afterwards, do not let the stale
            # parent link resurrect that newer independent deletion.
            if child.deleted_at != deleted_at:
                should_restore = False
            if child.purge_after != purge_after:
                should_restore = False
            if should_restore and (not child.purge_after or child.purge_after <= now):
                raise ValidationError({"record": "A cascaded Trash child has expired and the parent can no longer be fully restored."})
        resolved.append((link, child, should_restore))

    restored = 0
    restored_at = timezone.now()
    for link, child, should_restore in resolved:
        if should_restore:
            if not restore_from_trash(child):
                raise ValidationError({"record": "A cascaded Trash child could not be restored."})
            restored += 1
        link.restored_at = restored_at
        link.save(update_fields=("restored_at", "updated_at"))
    return restored


def active_cascade_child_ids(*, company, child_type: str) -> set[str]:
    """Return active cascade-owned child PKs for Record Management de-duplication."""

    from apps.core.models import TrashCascadeLink

    return set(
        TrashCascadeLink.objects.for_company(company)
        .filter(child_type=child_type, restored_at__isnull=True)
        .values_list("child_id", flat=True)
    )


def active_cascade_child_count(*, root, child_type: str | None = None) -> int:
    """Count children currently owned by a root Trash cascade."""

    from apps.core.models import TrashCascadeLink

    rows = TrashCascadeLink.objects.for_company(root.company).filter(
        root_type=_model_label(root), root_id=str(root.pk), restored_at__isnull=True
    )
    if child_type:
        rows = rows.filter(child_type=child_type)
    return rows.count()


def active_trash(queryset):
    return queryset.filter(deleted_at__isnull=False, purge_after__gt=timezone.now())
