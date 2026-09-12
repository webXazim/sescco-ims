from __future__ import annotations

from typing import Mapping

from apps.core.models import AuditArea
from apps.core.services.lifecycle import (
    LifecycleAction,
    LifecycleBlocker,
    LifecyclePolicy,
    register_lifecycle_policy,
)
from apps.inventory.models import InventoryLocation, StockItem, Supplier, Unit


class UnitLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INVENTORY
    object_type = "inventory.Unit"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: Unit) -> str:
        return instance.symbol

    def dependency_evidence(self, instance: Unit, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.ARCHIVE:
            return {"active_stock_records": instance.stock_items.filter(status=StockItem.Status.ACTIVE, deleted_at__isnull=True).count()}
        if action is LifecycleAction.DELETE:
            return {
                "stock_records": instance.stock_items.count(),
                "import_jobs": instance.import_jobs.count() if hasattr(instance, "import_jobs") else 0,
            }
        return {}

    def blockers(self, instance: Unit, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="unit", message="This unit is already archived."),)
            if evidence.get("active_stock_records", 0):
                return (LifecycleBlocker(code="active_stock_records", field="unit", label="Active stock records", count=evidence["active_stock_records"], message="Archive or change active stock records before archiving this unit."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="unit", message="This unit is not archived."),)
            return ()
        if action is LifecycleAction.DELETE:
            total = sum(evidence.values())
            if total:
                return (LifecycleBlocker(code="historical_records_exist", field="unit", label="Historical references", count=total, message="This unit has stock or import history. Archive it instead of deleting it."),)
            return ()
        return ()


class SupplierLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INVENTORY
    object_type = "inventory.Supplier"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: Supplier) -> str:
        return instance.name

    def dependency_evidence(self, instance: Supplier, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.DELETE:
            return {
                "stock_records": StockItem.objects.for_company(instance.company).filter(
                    normalized_supplier_name=instance.normalized_name,
                    normalized_supplier_phone=instance.normalized_phone,
                ).count()
            }
        return {}

    def blockers(self, instance: Supplier, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="supplier", message="This material supplier is already archived."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="supplier", message="This material supplier is not archived."),)
            return ()
        if action is LifecycleAction.DELETE:
            if evidence.get("stock_records", 0):
                return (LifecycleBlocker(code="historical_records_exist", field="supplier", label="Stock records", count=evidence["stock_records"], message="This supplier identity appears in Inventory history. Archive it instead of deleting it."),)
            return ()
        return ()


class StockItemLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INVENTORY
    object_type = "inventory.StockItem"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: StockItem) -> str:
        return str(instance.reference)[:8].upper()

    def dependency_evidence(self, instance: StockItem, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.ARCHIVE:
            return {"current_quantity": 1 if instance.current_quantity else 0}
        if action is LifecycleAction.DELETE:
            return {
                "current_quantity": 1 if instance.current_quantity else 0,
                "movements": instance.movements.count(),
                "documents": instance.documents.count(),
                "import_rows": instance.import_rows.count() if hasattr(instance, "import_rows") else 0,
                "transfer_lines_source": instance.outgoing_transfer_lines.count() if hasattr(instance, "outgoing_transfer_lines") else 0,
                "transfer_lines_destination": instance.incoming_transfer_lines.count() if hasattr(instance, "incoming_transfer_lines") else 0,
            }
        return {}

    def blockers(self, instance: StockItem, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if action is LifecycleAction.ARCHIVE:
            if instance.status == StockItem.Status.ARCHIVED or instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="stock", message="This stock record is already archived."),)
            if evidence.get("current_quantity", 0):
                return (LifecycleBlocker(code="stock_balance_exists", field="stock", message="A stock record can be archived only when its balance is zero."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if instance.status != StockItem.Status.ARCHIVED and not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="stock", message="This stock record is not archived."),)
            if instance.location.archived_at or not instance.location.is_active:
                return (LifecycleBlocker(code="location_inactive", field="stock", message="Restore the inventory location before restoring this stock record."),)
            if instance.project_id and instance.project.status != instance.project.Status.ACTIVE:
                return (LifecycleBlocker(code="project_inactive", field="stock", message="Reactivate the project before restoring this stock record."),)
            if instance.unit.archived_at or not instance.unit.is_active:
                return (LifecycleBlocker(code="unit_inactive", field="stock", message="Restore the unit before restoring this stock record."),)
            return ()
        if action is LifecycleAction.DELETE:
            total = sum(evidence.values())
            if total:
                return (LifecycleBlocker(code="historical_records_exist", field="stock", label="Inventory history", count=total, message="This stock record has balance, movement, document, import, or transfer history. Archive it instead of deleting it."),)
            return ()
        return ()


class InventoryLocationLifecyclePolicy(LifecyclePolicy):
    area = AuditArea.INVENTORY
    object_type = "inventory.InventoryLocation"
    supported_actions = frozenset({LifecycleAction.ARCHIVE, LifecycleAction.RESTORE, LifecycleAction.DELETE})
    reason_required_actions = frozenset({LifecycleAction.ARCHIVE})
    confirmation_required_actions = frozenset({LifecycleAction.DELETE})

    def confirmation_token(self, instance: InventoryLocation) -> str:
        return instance.code

    def dependency_evidence(self, instance: InventoryLocation, action: LifecycleAction) -> Mapping[str, int]:
        if action is LifecycleAction.ARCHIVE:
            return {"quantity_bearing_stock": instance.stock_items.filter(current_quantity__gt=0, deleted_at__isnull=True).count()}
        if action is LifecycleAction.DELETE:
            return {
                "stock_records": instance.stock_items.count(),
                "outgoing_transfers": instance.outgoing_transfers.count(),
                "incoming_transfers": instance.incoming_transfers.count(),
            }
        return {}

    def blockers(self, instance: InventoryLocation, action: LifecycleAction, *, evidence: Mapping[str, int]):
        if instance.location_type == InventoryLocation.Type.PROJECT:
            return (LifecycleBlocker(code="project_managed_location", field="location", message="Project inventory locations follow the project lifecycle. Manage this location from the Project record."),)
        if action is LifecycleAction.ARCHIVE:
            if instance.archived_at:
                return (LifecycleBlocker(code="already_archived", field="location", message="This inventory location is already archived."),)
            if evidence.get("quantity_bearing_stock", 0):
                return (LifecycleBlocker(code="stock_balance_exists", field="location", label="Stock records with balance", count=evidence["quantity_bearing_stock"], message="Move or use all stock to zero before archiving this location."),)
            return ()
        if action is LifecycleAction.RESTORE:
            if not instance.archived_at:
                return (LifecycleBlocker(code="not_archived", field="location", message="This inventory location is not archived."),)
            return ()
        if action is LifecycleAction.DELETE:
            total = sum(evidence.values())
            if total:
                return (LifecycleBlocker(code="historical_records_exist", field="location", label="Inventory references", count=total, message="This location has stock or transfer history. Archive it instead of deleting it."),)
            return ()
        return ()


register_lifecycle_policy(Unit, UnitLifecyclePolicy())
register_lifecycle_policy(Supplier, SupplierLifecyclePolicy())
register_lifecycle_policy(StockItem, StockItemLifecyclePolicy())
register_lifecycle_policy(InventoryLocation, InventoryLocationLifecyclePolicy())
