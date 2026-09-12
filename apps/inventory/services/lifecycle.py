from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import CompanyMembership
from apps.accounts.permissions import membership_has_capability
from apps.accounts.roles import Capability
from apps.core.services.lifecycle import LifecycleAction, record_lifecycle_action, require_lifecycle_action
from apps.core.trash import move_to_trash
from apps.inventory.models import InventoryLocation, StockItem, Supplier, Unit


def _require_manage_inventory(membership: CompanyMembership) -> None:
    if not membership_has_capability(membership, Capability.MANAGE_INVENTORY):
        raise PermissionDenied("Inventory management authority is required for this lifecycle action.")


def _snapshot(instance) -> dict[str, object]:
    payload: dict[str, object] = {
        "pk": str(instance.pk),
        "label": str(instance),
        "archived_at": instance.archived_at.isoformat() if getattr(instance, "archived_at", None) else "",
        "archived_reason": getattr(instance, "archived_reason", ""),
        "deleted_at": instance.deleted_at.isoformat() if getattr(instance, "deleted_at", None) else "",
    }
    if hasattr(instance, "is_active"):
        payload["is_active"] = instance.is_active
    if isinstance(instance, StockItem):
        payload.update(status=instance.status, current_quantity=str(instance.current_quantity))
    return payload


def _fields_for_archive(instance, archived: bool, reason: str = "") -> tuple[str, ...]:
    instance.archived_at = timezone.now() if archived else None
    instance.archived_reason = (reason or "").strip() if archived else ""
    if hasattr(instance, "is_active"):
        instance.is_active = not archived
    if isinstance(instance, StockItem):
        instance.status = StockItem.Status.ARCHIVED if archived else StockItem.Status.ACTIVE
    fields = ["archived_at", "archived_reason", "updated_at"]
    if hasattr(instance, "is_active"):
        fields.append("is_active")
    if isinstance(instance, StockItem):
        fields.append("status")
    return tuple(fields)


def _archive(*, instance, actor_membership: CompanyMembership, reason: str, audit_action: str, request=None):
    decision = require_lifecycle_action(instance, LifecycleAction.ARCHIVE, reason=reason)
    before = _snapshot(instance)
    fields = _fields_for_archive(instance, True, reason)
    instance.full_clean()
    instance.save(update_fields=fields)
    record_lifecycle_action(instance=instance, decision=decision, actor_membership=actor_membership, before=before, after=_snapshot(instance), reason=reason, audit_action=audit_action, request=request)
    return instance


def _restore(*, instance, actor_membership: CompanyMembership, audit_action: str, request=None):
    decision = require_lifecycle_action(instance, LifecycleAction.RESTORE)
    before = _snapshot(instance)
    previous_reason = instance.archived_reason
    fields = _fields_for_archive(instance, False)
    instance.full_clean()
    instance.save(update_fields=fields)
    record_lifecycle_action(instance=instance, decision=decision, actor_membership=actor_membership, before=before, after=_snapshot(instance), audit_action=audit_action, metadata={"previous_archive_reason": previous_reason}, request=request)
    return instance


def _trash_unused(*, instance, actor_membership: CompanyMembership, confirmation: str, reason: str, audit_action: str, request=None):
    decision = require_lifecycle_action(instance, LifecycleAction.DELETE, confirmation=confirmation)
    before = _snapshot(instance)
    move_to_trash(instance, user=actor_membership.user, reason=reason)
    record_lifecycle_action(instance=instance, decision=decision, actor_membership=actor_membership, before=before, after=_snapshot(instance), reason=reason, audit_action=audit_action, metadata={"guard": "unused-master-only", "retention_days": 30}, request=request)
    return instance


@transaction.atomic
def archive_unit(*, actor_membership, unit_id, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    unit = Unit.objects.select_for_update().get(pk=unit_id, company=actor_membership.company, deleted_at__isnull=True)
    return _archive(instance=unit, actor_membership=actor_membership, reason=reason, audit_action="inventory.unit.archived", request=request)


@transaction.atomic
def restore_unit(*, actor_membership, unit_id, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    unit = Unit.objects.select_for_update().get(pk=unit_id, company=actor_membership.company, deleted_at__isnull=True)
    return _restore(instance=unit, actor_membership=actor_membership, audit_action="inventory.unit.archive_restored", request=request)


@transaction.atomic
def trash_unused_unit(*, actor_membership, unit_id, confirmation, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    unit = Unit.objects.select_for_update().get(pk=unit_id, company=actor_membership.company, deleted_at__isnull=True)
    return _trash_unused(instance=unit, actor_membership=actor_membership, confirmation=confirmation, reason=reason, audit_action="inventory.unit.trashed_unused", request=request)


@transaction.atomic
def archive_supplier(*, actor_membership, supplier_id, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id, company=actor_membership.company, deleted_at__isnull=True)
    return _archive(instance=supplier, actor_membership=actor_membership, reason=reason, audit_action="inventory.supplier.archived", request=request)


@transaction.atomic
def restore_supplier(*, actor_membership, supplier_id, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id, company=actor_membership.company, deleted_at__isnull=True)
    return _restore(instance=supplier, actor_membership=actor_membership, audit_action="inventory.supplier.archive_restored", request=request)


@transaction.atomic
def trash_unused_supplier(*, actor_membership, supplier_id, confirmation, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    supplier = Supplier.objects.select_for_update().get(pk=supplier_id, company=actor_membership.company, deleted_at__isnull=True)
    return _trash_unused(instance=supplier, actor_membership=actor_membership, confirmation=confirmation, reason=reason, audit_action="inventory.supplier.trashed_unused", request=request)


@transaction.atomic
def archive_stock_item(*, actor_membership, stock_item_id, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    item = StockItem.objects.select_for_update().get(pk=stock_item_id, company=actor_membership.company, deleted_at__isnull=True)
    return _archive(instance=item, actor_membership=actor_membership, reason=reason, audit_action="inventory.stock.archived", request=request)


@transaction.atomic
def restore_stock_item(*, actor_membership, stock_item_id, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    item = StockItem.objects.select_for_update().select_related("location", "project", "unit").get(pk=stock_item_id, company=actor_membership.company, deleted_at__isnull=True)
    return _restore(instance=item, actor_membership=actor_membership, audit_action="inventory.stock.archive_restored", request=request)


@transaction.atomic
def trash_unused_stock_item(*, actor_membership, stock_item_id, confirmation, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    item = StockItem.objects.select_for_update().get(pk=stock_item_id, company=actor_membership.company, deleted_at__isnull=True)
    return _trash_unused(instance=item, actor_membership=actor_membership, confirmation=confirmation, reason=reason, audit_action="inventory.stock.trashed_unused", request=request)


@transaction.atomic
def archive_location(*, actor_membership, location_id, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    location = InventoryLocation.objects.select_for_update().get(pk=location_id, company=actor_membership.company, deleted_at__isnull=True)
    return _archive(instance=location, actor_membership=actor_membership, reason=reason, audit_action="inventory.location.archived", request=request)


@transaction.atomic
def restore_location(*, actor_membership, location_id, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    location = InventoryLocation.objects.select_for_update().get(pk=location_id, company=actor_membership.company, deleted_at__isnull=True)
    return _restore(instance=location, actor_membership=actor_membership, audit_action="inventory.location.archive_restored", request=request)


@transaction.atomic
def trash_unused_location(*, actor_membership, location_id, confirmation, reason, request: HttpRequest | None = None):
    _require_manage_inventory(actor_membership)
    location = InventoryLocation.objects.select_for_update().get(pk=location_id, company=actor_membership.company, deleted_at__isnull=True)
    return _trash_unused(instance=location, actor_membership=actor_membership, confirmation=confirmation, reason=reason, audit_action="inventory.location.trashed_unused", request=request)
