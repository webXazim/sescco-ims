from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import transaction
from django.utils import timezone

from apps.accounts.permissions import user_has_capability_for_company
from apps.accounts.roles import Capability

from ..models import (
    InventoryLocation,
    StockItem,
    StockMovement,
    StockTransfer,
    StockTransferLine,
)
from .stock import (
    InactiveStockError,
    InsufficientStockError,
    InventoryOperationError,
    _create_movement,
    _require_inventory_edit,
    _save_balance,
    _validate_operation_date,
    _validate_positive_quantity,
)


class TransferAlreadyReversedError(InventoryOperationError):
    pass


@dataclass(frozen=True)
class TransferAllocation:
    source_stock_item: StockItem
    outcome: str
    quantity: Decimal


@dataclass(frozen=True)
class TransferResult:
    transfer: StockTransfer
    duplicate_submission: bool = False


def _movement_key(transfer_key: UUID, line_id: int, leg: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"ims-transfer:{transfer_key}:{line_id}:{leg}")


def _require_active_location(location: InventoryLocation, label: str) -> None:
    if not location.accepts_stock_activity:
        raise InactiveStockError(f"The {label} location is not available for stock activity.")


def _destination_item(
    *, source: StockItem, destination: InventoryLocation, condition: str, user
) -> StockItem:
    exact = (
        StockItem.objects.for_company(destination.company).select_for_update(of=("self",))
        .filter(
            location=destination,
            normalized_material_name=source.normalized_material_name,
            normalized_supplier_name=source.normalized_supplier_name,
            normalized_supplier_phone=source.normalized_supplier_phone,
            condition=condition,
        )
        .first()
    )
    if exact:
        if exact.unit_id != source.unit_id:
            raise InventoryOperationError("Matching destination stock uses a different unit.")
        if exact.deleted_at:
            raise InactiveStockError("Matching destination stock is currently in Trash.")
        if exact.status == StockItem.Status.ARCHIVED or exact.archived_at:
            raise InactiveStockError(
                "Matching destination stock is archived. Restore the stock record before transferring into it."
            )
        return exact

    item = StockItem(
        company=destination.company,
        project=destination.project,
        location=destination,
        condition=condition,
        material_name=source.material_name,
        description=source.description,
        supplier_name=source.supplier_name,
        supplier_phone=source.supplier_phone,
        supplier_location=source.supplier_location,
        unit=source.unit,
        minimum_quantity=Decimal("0"),
        notes=source.notes,
        created_by=user,
        updated_by=user,
    )
    item.save(_inventory_service=True)
    return item


def transfer_stock(
    *,
    user,
    idempotency_key: UUID,
    source_location: InventoryLocation,
    destination_location: InventoryLocation,
    transfer_date: date,
    allocations: list[TransferAllocation],
    document_reference: str = "",
    notes: str = "",
    attachment=None,
) -> TransferResult:
    if source_location.company_id != destination_location.company_id:
        raise InventoryOperationError("Source and destination must belong to the same company.")
    company = source_location.company
    _require_inventory_edit(user, company)
    existing = StockTransfer.objects.for_company(company).filter(idempotency_key=idempotency_key).first()
    if existing:
        return TransferResult(existing, duplicate_submission=True)
    _validate_operation_date(transfer_date)
    if source_location.pk == destination_location.pk:
        raise InventoryOperationError("Source and destination must be different.")
    if not allocations:
        raise InventoryOperationError("Add at least one transfer quantity.")

    normalized: list[tuple[int, str, Decimal]] = []
    totals: dict[int, Decimal] = defaultdict(Decimal)
    for allocation in allocations:
        if allocation.outcome not in StockTransferLine.Outcome.values:
            raise InventoryOperationError("Choose a valid condition outcome.")
        quantity = _validate_positive_quantity(allocation.quantity)
        item_id = allocation.source_stock_item.pk
        normalized.append((item_id, allocation.outcome, quantity))
        totals[item_id] += quantity

    with transaction.atomic():
        locations = {
            location.pk: location
            for location in InventoryLocation.objects.for_company(company).select_for_update(of=("self",))
            .select_related("project")
            .filter(pk__in=(source_location.pk, destination_location.pk))
            .order_by("pk")
        }
        source_location = locations[source_location.pk]
        destination_location = locations[destination_location.pk]
        _require_active_location(source_location, "source")
        _require_active_location(destination_location, "destination")

        source_items = {
            item.pk: item
            for item in StockItem.objects.for_company(company).select_for_update(of=("self",))
            .select_related("location", "location__project", "project", "unit")
            .filter(pk__in=totals)
            .order_by("pk")
        }
        if len(source_items) != len(totals):
            raise InventoryOperationError("One or more source stock records no longer exist.")
        for item_id, total in totals.items():
            item = source_items[item_id]
            if item.location_id != source_location.pk:
                raise InventoryOperationError(
                    "Every stock item must belong to the source location."
                )
            if item.status != StockItem.Status.ACTIVE or item.deleted_at:
                raise InactiveStockError("Archived or deleted stock cannot be transferred.")
            if total > item.current_quantity:
                raise InsufficientStockError(
                    f"Only {item.quantity_display} of {item.material_name} is available."
                )

        transfer = StockTransfer(
            company=company,
            idempotency_key=idempotency_key,
            source_location=source_location,
            destination_location=destination_location,
            transfer_date=transfer_date,
            document_reference=document_reference,
            notes=notes,
            attachment=attachment,
            created_by=user,
        )
        transfer.save()

        for item_id, outcome, quantity in normalized:
            source = source_items[item_id]
            destination = None
            if outcome != StockTransferLine.Outcome.LOST:
                destination = _destination_item(
                    source=source,
                    destination=destination_location,
                    condition=outcome,
                    user=user,
                )
            unit_price = (
                Decimal("0")
                if outcome == StockTransferLine.Outcome.NO_VALUE
                else source.latest_unit_price
            )
            line = StockTransferLine(
                transfer=transfer,
                source_stock_item=source,
                destination_stock_item=destination,
                outcome=outcome,
                quantity=quantity,
                source_condition_snapshot=source.condition,
                unit_price_snapshot=unit_price,
            )
            line.save()

            source_previous = source.current_quantity
            source_new = source_previous - quantity
            _create_movement(
                stock_item=source,
                movement_type=(
                    StockMovement.Type.LOSS
                    if outcome == StockTransferLine.Outcome.LOST
                    else StockMovement.Type.TRANSFER_OUT
                ),
                quantity=quantity,
                previous_balance=source_previous,
                new_balance=source_new,
                movement_date=transfer_date,
                idempotency_key=_movement_key(idempotency_key, line.pk, "out"),
                user=user,
                unit_price=source.latest_unit_price,
                invoice_reference=document_reference,
                purpose=f"Transfer to {destination_location.code}",
                reason=(
                    "Lost during project closeout or stock transfer"
                    if outcome == "lost"
                    else ""
                ),
                notes=notes,
                transfer_line=line,
            )
            _save_balance(stock_item=source, new_balance=source_new, user=user)

            if destination:
                destination_previous = destination.current_quantity
                destination_new = destination_previous + quantity
                _create_movement(
                    stock_item=destination,
                    movement_type=StockMovement.Type.TRANSFER_IN,
                    quantity=quantity,
                    previous_balance=destination_previous,
                    new_balance=destination_new,
                    movement_date=transfer_date,
                    idempotency_key=_movement_key(idempotency_key, line.pk, "in"),
                    user=user,
                    unit_price=unit_price,
                    invoice_reference=document_reference,
                    purpose=f"Transfer from {source_location.code}",
                    notes=notes,
                    transfer_line=line,
                )
                balance_kwargs = {}
                if destination.latest_unit_price is None or outcome == "no_value":
                    balance_kwargs["latest_unit_price"] = unit_price
                _save_balance(
                    stock_item=destination,
                    new_balance=destination_new,
                    user=user,
                    **balance_kwargs,
                )

        return TransferResult(transfer)


def reverse_transfer(
    *, transfer: StockTransfer, user, idempotency_key: UUID, reason: str
) -> TransferResult:
    if not user_has_capability_for_company(user, transfer.company, Capability.MANAGE_INVENTORY):
        raise InventoryOperationError("Only an inventory manager can reverse transfers.")
    if not reason.strip():
        raise InventoryOperationError("A reversal reason is required.")
    duplicate = StockTransfer.objects.for_company(transfer.company).filter(reversal_idempotency_key=idempotency_key).first()
    if duplicate:
        return TransferResult(duplicate, duplicate_submission=True)

    with transaction.atomic():
        transfer = (
            StockTransfer.objects.for_company(transfer.company).select_for_update(of=("self",))
            .select_related("source_location__project", "destination_location__project")
            .get(pk=transfer.pk)
        )
        if transfer.status == StockTransfer.Status.REVERSED:
            raise TransferAlreadyReversedError("This transfer has already been reversed.")
        _require_active_location(transfer.source_location, "source")
        _require_active_location(transfer.destination_location, "destination")

        lines = list(
            transfer.lines.select_related("source_stock_item", "destination_stock_item").all()
        )
        item_ids = {
            item_id
            for line in lines
            for item_id in (line.source_stock_item_id, line.destination_stock_item_id)
            if item_id
        }
        locked_items = {
            item.pk: item
            for item in StockItem.objects.for_company(transfer.company).select_for_update(of=("self",))
            .select_related("location", "project", "unit")
            .filter(pk__in=item_ids)
            .order_by("pk")
        }
        for line in lines:
            if line.destination_stock_item_id:
                destination = locked_items[line.destination_stock_item_id]
                if destination.current_quantity < line.quantity:
                    raise InsufficientStockError(
                        f"{destination.material_name} no longer has enough destination stock "
                        "to reverse."
                    )

        for line in reversed(lines):
            movements = list(line.movements.select_related("stock_item").order_by("pk"))
            inbound = next(
                (m for m in movements if m.movement_type == StockMovement.Type.TRANSFER_IN), None
            )
            outbound = next(
                (
                    m
                    for m in movements
                    if m.movement_type in {StockMovement.Type.TRANSFER_OUT, StockMovement.Type.LOSS}
                ),
                None,
            )
            if inbound:
                item = locked_items[inbound.stock_item_id]
                previous = item.current_quantity
                new = previous - line.quantity
                _create_movement(
                    stock_item=item,
                    movement_type=StockMovement.Type.REVERSAL,
                    quantity=line.quantity,
                    previous_balance=previous,
                    new_balance=new,
                    movement_date=timezone.localdate(),
                    idempotency_key=_movement_key(idempotency_key, line.pk, "reverse-in"),
                    user=user,
                    reason=reason,
                    reversal_of=inbound,
                    transfer_line=line,
                )
                _save_balance(stock_item=item, new_balance=new, user=user)
            if outbound:
                item = locked_items[outbound.stock_item_id]
                previous = item.current_quantity
                new = previous + line.quantity
                _create_movement(
                    stock_item=item,
                    movement_type=StockMovement.Type.REVERSAL,
                    quantity=line.quantity,
                    previous_balance=previous,
                    new_balance=new,
                    movement_date=timezone.localdate(),
                    idempotency_key=_movement_key(idempotency_key, line.pk, "reverse-out"),
                    user=user,
                    reason=reason,
                    reversal_of=outbound,
                    transfer_line=line,
                )
                _save_balance(stock_item=item, new_balance=new, user=user)

        transfer.status = StockTransfer.Status.REVERSED
        transfer.reversal_reason = reason.strip()
        transfer.reversal_idempotency_key = idempotency_key
        transfer.reversed_at = timezone.now()
        transfer.reversed_by = user
        transfer.save(
            _inventory_service=True,
            update_fields=(
                "status",
                "reversal_reason",
                "reversal_idempotency_key",
                "reversed_at",
                "reversed_by",
            ),
        )
        return TransferResult(transfer)
