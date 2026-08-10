from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.projects.models import Project

from ..models import StockItem, StockMovement, Supplier, Unit
from ..normalization import clean_display_text, normalize_phone, normalize_text


class InventoryOperationError(ValidationError):
    """Base exception for safe inventory-operation failures."""


class InsufficientStockError(InventoryOperationError):
    pass


class InactiveStockError(InventoryOperationError):
    pass


class MovementAlreadyReversedError(InventoryOperationError):
    pass


@dataclass(frozen=True)
class MovementResult:
    movement: StockMovement
    duplicate_submission: bool = False
    stock_item_created: bool = False


def _validate_operation_date(value: date) -> None:
    if value > timezone.localdate():
        raise InventoryOperationError("Movement date cannot be in the future.")


def _validate_positive_quantity(quantity: Decimal) -> Decimal:
    value = Decimal(quantity)
    if value <= 0:
        raise InventoryOperationError("Quantity must be greater than zero.")
    return value


def _existing_idempotent_result(idempotency_key: UUID) -> MovementResult | None:
    movement = (
        StockMovement.objects.select_related("stock_item", "stock_item__unit")
        .filter(idempotency_key=idempotency_key)
        .first()
    )
    if movement:
        return MovementResult(movement=movement, duplicate_submission=True)
    return None


def _save_balance(
    *,
    stock_item: StockItem,
    new_balance: Decimal,
    user,
    latest_unit_price: Decimal | None | object = ...,  # Ellipsis means unchanged.
    latest_addition_date: date | None | object = ...,
) -> None:
    stock_item.current_quantity = new_balance
    stock_item.updated_by = user
    update_fields = ["current_quantity", "updated_by", "updated_at"]
    if latest_unit_price is not ...:
        stock_item.latest_unit_price = latest_unit_price
        update_fields.append("latest_unit_price")
    if latest_addition_date is not ...:
        stock_item.latest_addition_date = latest_addition_date
        update_fields.append("latest_addition_date")
    stock_item.save(_inventory_service=True, update_fields=update_fields)


def _create_movement(
    *,
    stock_item: StockItem,
    movement_type: str,
    quantity: Decimal,
    previous_balance: Decimal,
    new_balance: Decimal,
    movement_date: date,
    idempotency_key: UUID,
    user,
    unit_price: Decimal | None = None,
    invoice_reference: str = "",
    purpose: str = "",
    recipient: str = "",
    reason: str = "",
    notes: str = "",
    attachment=None,
    reversal_of: StockMovement | None = None,
) -> StockMovement:
    movement = StockMovement(
        stock_item=stock_item,
        movement_type=movement_type,
        quantity=quantity,
        previous_balance=previous_balance,
        new_balance=new_balance,
        unit_price=unit_price,
        movement_date=movement_date,
        invoice_reference=invoice_reference,
        purpose=purpose,
        recipient=recipient,
        reason=reason,
        notes=notes,
        attachment=attachment,
        reversal_of=reversal_of,
        created_by=user,
        idempotency_key=idempotency_key,
    )
    try:
        movement.save()
    except Exception:
        if (
            movement.attachment
            and movement.attachment.name
            and getattr(movement.attachment, "_committed", False)
        ):
            movement.attachment.storage.delete(movement.attachment.name)
        raise
    return movement


def _require_active_stock_item(stock_item: StockItem) -> None:
    if stock_item.deleted_at or stock_item.project.deleted_at:
        raise InactiveStockError("Deleted stock records cannot receive new activity.")
    if stock_item.status != StockItem.Status.ACTIVE:
        raise InactiveStockError("Archived stock records cannot receive new activity.")
    if stock_item.project.status != Project.Status.ACTIVE:
        raise InactiveStockError("Completed or archived projects cannot receive new activity.")


def add_stock(
    *,
    user,
    idempotency_key: UUID,
    quantity: Decimal,
    movement_date: date,
    project: Project,
    material_name: str,
    supplier_name: str,
    supplier_phone: str,
    unit: Unit,
    description: str = "",
    supplier_location: str = "",
    minimum_quantity: Decimal = Decimal("0"),
    unit_price: Decimal | None = None,
    invoice_reference: str = "",
    notes: str = "",
    attachment=None,
    confirm_similar: bool = False,
) -> MovementResult:
    """Add stock to an exact record or create a new stock record atomically."""

    if project.deleted_at or unit.deleted_at:
        raise InactiveStockError("Deleted projects and units cannot receive new stock.")
    duplicate = _existing_idempotent_result(idempotency_key)
    if duplicate:
        return duplicate

    quantity = _validate_positive_quantity(quantity)
    _validate_operation_date(movement_date)
    if unit_price is not None and Decimal(unit_price) < 0:
        raise InventoryOperationError("Unit price cannot be negative.")
    if project.status != Project.Status.ACTIVE:
        raise InactiveStockError("Only active projects can receive stock.")
    if not unit.is_active:
        raise InactiveStockError("Only active units can be used for new stock activity.")

    normalized_material = normalize_text(material_name)
    normalized_supplier = normalize_text(supplier_name)
    normalized_phone = normalize_phone(supplier_phone)
    if not all((normalized_material, normalized_supplier, normalized_phone)):
        raise InventoryOperationError("Material, supplier, and supplier phone are required.")

    try:
        with transaction.atomic():
            # Lock the project before resolving a possibly-new identity. This serializes
            # concurrent first additions within one project, so two requests cannot both
            # conclude that the same stock identity is missing and race to create it.
            locked_project = Project.objects.select_for_update().get(pk=project.pk)
            if locked_project.status != Project.Status.ACTIVE:
                raise InactiveStockError("Only active projects can receive stock.")

            # Keep suppliers introduced through imports and integrations available in
            # the managed supplier picker without changing historical stock snapshots.
            Supplier.objects.get_or_create(
                normalized_name=normalized_supplier,
                normalized_phone=normalized_phone,
                defaults={
                    "name": supplier_name,
                    "phone": supplier_phone,
                    "location": supplier_location,
                },
            )

            exact = (
                StockItem.objects.select_for_update()
                .select_related("project", "unit")
                .filter(
                    project=locked_project,
                    normalized_material_name=normalized_material,
                    normalized_supplier_name=normalized_supplier,
                    normalized_supplier_phone=normalized_phone,
                )
                .first()
            )
            stock_item_created = False
            if exact:
                stock_item = exact
                _require_active_stock_item(stock_item)
                if stock_item.unit_id != unit.pk:
                    raise InventoryOperationError(
                        f"This stock record uses {stock_item.unit.name} "
                        f"({stock_item.unit.symbol}), not {unit.name} ({unit.symbol})."
                    )
            else:
                similar = StockItem.objects.filter(
                    project=locked_project,
                    normalized_material_name=normalized_material,
                    normalized_supplier_name=normalized_supplier,
                ).exclude(normalized_supplier_phone=normalized_phone)
                if similar.exists() and not confirm_similar:
                    raise InventoryOperationError(
                        "A similar stock record has the same project, material, and supplier "
                        "but a different phone number. Review it before creating a separate record."
                    )
                stock_item = StockItem(
                    project=locked_project,
                    material_name=material_name,
                    description=description,
                    supplier_name=supplier_name,
                    supplier_phone=supplier_phone,
                    supplier_location=supplier_location,
                    unit=unit,
                    minimum_quantity=minimum_quantity,
                    notes="",
                    created_by=user,
                    updated_by=user,
                )
                stock_item.save()
                stock_item_created = True

            previous_balance = stock_item.current_quantity
            new_balance = previous_balance + quantity
            balance_kwargs = {
                "stock_item": stock_item,
                "new_balance": new_balance,
                "user": user,
                "latest_addition_date": movement_date,
            }
            if unit_price is not None:
                balance_kwargs["latest_unit_price"] = unit_price
            _save_balance(**balance_kwargs)
            movement = _create_movement(
                stock_item=stock_item,
                movement_type=StockMovement.Type.ADDITION,
                quantity=quantity,
                previous_balance=previous_balance,
                new_balance=new_balance,
                movement_date=movement_date,
                idempotency_key=idempotency_key,
                user=user,
                unit_price=unit_price,
                invoice_reference=invoice_reference,
                notes=notes,
                attachment=attachment,
            )
            return MovementResult(
                movement=movement,
                stock_item_created=stock_item_created,
            )
    except IntegrityError:
        duplicate = _existing_idempotent_result(idempotency_key)
        if duplicate:
            return duplicate
        raise


def add_opening_stock(
    *,
    stock_item: StockItem,
    user,
    idempotency_key: UUID,
    quantity: Decimal,
    movement_date: date,
    unit_price: Decimal | None = None,
    invoice_reference: str = "",
    notes: str = "",
) -> MovementResult:
    """Create an opening movement for imports and administrator setup."""

    if not getattr(user, "is_inventory_admin", False):
        raise InventoryOperationError("Only an administrator can create opening stock.")
    duplicate = _existing_idempotent_result(idempotency_key)
    if duplicate:
        return duplicate
    quantity = _validate_positive_quantity(quantity)
    _validate_operation_date(movement_date)
    if unit_price is not None and Decimal(unit_price) < 0:
        raise InventoryOperationError("Unit price cannot be negative.")

    try:
        with transaction.atomic():
            locked = (
                StockItem.objects.select_for_update()
                .select_related("project", "unit")
                .get(pk=stock_item.pk)
            )
            _require_active_stock_item(locked)
            if locked.movements.exists():
                raise InventoryOperationError(
                    "Opening stock can only be created before the first movement."
                )
            previous_balance = locked.current_quantity
            new_balance = previous_balance + quantity
            balance_kwargs = {
                "stock_item": locked,
                "new_balance": new_balance,
                "user": user,
                "latest_addition_date": movement_date,
            }
            if unit_price is not None:
                balance_kwargs["latest_unit_price"] = unit_price
            _save_balance(**balance_kwargs)
            movement = _create_movement(
                stock_item=locked,
                movement_type=StockMovement.Type.OPENING,
                quantity=quantity,
                previous_balance=previous_balance,
                new_balance=new_balance,
                movement_date=movement_date,
                idempotency_key=idempotency_key,
                user=user,
                unit_price=unit_price,
                invoice_reference=invoice_reference,
                notes=notes,
            )
            return MovementResult(movement=movement)
    except IntegrityError:
        duplicate = _existing_idempotent_result(idempotency_key)
        if duplicate:
            return duplicate
        raise


def use_stock(
    *,
    stock_item: StockItem,
    user,
    idempotency_key: UUID,
    quantity: Decimal,
    movement_date: date,
    purpose: str,
    recipient: str = "",
    invoice_reference: str = "",
    notes: str = "",
    attachment=None,
) -> MovementResult:
    duplicate = _existing_idempotent_result(idempotency_key)
    if duplicate:
        return duplicate
    quantity = _validate_positive_quantity(quantity)
    _validate_operation_date(movement_date)
    if not clean_display_text(purpose):
        raise InventoryOperationError("A usage purpose is required.")

    try:
        with transaction.atomic():
            locked = (
                StockItem.objects.select_for_update()
                .select_related("project", "unit")
                .get(pk=stock_item.pk)
            )
            _require_active_stock_item(locked)
            previous_balance = locked.current_quantity
            if quantity > previous_balance:
                raise InsufficientStockError(f"Only {locked.quantity_display} is available.")
            new_balance = previous_balance - quantity
            _save_balance(stock_item=locked, new_balance=new_balance, user=user)
            movement = _create_movement(
                stock_item=locked,
                movement_type=StockMovement.Type.USAGE,
                quantity=quantity,
                previous_balance=previous_balance,
                new_balance=new_balance,
                movement_date=movement_date,
                idempotency_key=idempotency_key,
                user=user,
                unit_price=locked.latest_unit_price,
                invoice_reference=invoice_reference,
                purpose=purpose,
                recipient=recipient,
                notes=notes,
                attachment=attachment,
            )
            return MovementResult(movement=movement)
    except IntegrityError:
        duplicate = _existing_idempotent_result(idempotency_key)
        if duplicate:
            return duplicate
        raise


def adjust_stock(
    *,
    stock_item: StockItem,
    user,
    idempotency_key: UUID,
    direction: str,
    quantity: Decimal,
    movement_date: date,
    reason: str,
    invoice_reference: str = "",
    notes: str = "",
) -> MovementResult:
    duplicate = _existing_idempotent_result(idempotency_key)
    if duplicate:
        return duplicate
    quantity = _validate_positive_quantity(quantity)
    _validate_operation_date(movement_date)
    reason = clean_display_text(reason)
    if not reason:
        raise InventoryOperationError("An adjustment reason is required.")
    if direction not in {"increase", "decrease"}:
        raise InventoryOperationError("Choose whether the adjustment increases or decreases stock.")

    try:
        with transaction.atomic():
            locked = (
                StockItem.objects.select_for_update()
                .select_related("project", "unit")
                .get(pk=stock_item.pk)
            )
            _require_active_stock_item(locked)
            previous_balance = locked.current_quantity
            if direction == "increase":
                movement_type = StockMovement.Type.ADJUSTMENT_IN
                new_balance = previous_balance + quantity
            else:
                movement_type = StockMovement.Type.ADJUSTMENT_OUT
                if quantity > previous_balance:
                    raise InsufficientStockError(f"Only {locked.quantity_display} is available.")
                new_balance = previous_balance - quantity
            _save_balance(stock_item=locked, new_balance=new_balance, user=user)
            movement = _create_movement(
                stock_item=locked,
                movement_type=movement_type,
                quantity=quantity,
                previous_balance=previous_balance,
                new_balance=new_balance,
                movement_date=movement_date,
                idempotency_key=idempotency_key,
                user=user,
                unit_price=locked.latest_unit_price,
                invoice_reference=invoice_reference,
                reason=reason,
                notes=notes,
            )
            return MovementResult(movement=movement)
    except IntegrityError:
        duplicate = _existing_idempotent_result(idempotency_key)
        if duplicate:
            return duplicate
        raise


def _unreversed_additions(stock_item: StockItem):
    return StockMovement.objects.filter(
        stock_item=stock_item,
        movement_type__in=(StockMovement.Type.OPENING, StockMovement.Type.ADDITION),
        reversal__isnull=True,
    )


def _latest_unreversed_addition(stock_item: StockItem) -> StockMovement | None:
    return (
        _unreversed_additions(stock_item).order_by("-movement_date", "-created_at", "-pk").first()
    )


def _latest_unreversed_priced_addition(stock_item: StockItem) -> StockMovement | None:
    return (
        _unreversed_additions(stock_item)
        .filter(unit_price__isnull=False)
        .order_by("-movement_date", "-created_at", "-pk")
        .first()
    )


def reverse_movement(
    *,
    movement: StockMovement,
    user,
    idempotency_key: UUID,
    movement_date: date,
    reason: str,
) -> MovementResult:
    if not getattr(user, "is_inventory_admin", False):
        raise InventoryOperationError("Only an administrator can reverse stock movements.")
    duplicate = _existing_idempotent_result(idempotency_key)
    if duplicate:
        return duplicate
    _validate_operation_date(movement_date)
    reason = clean_display_text(reason)
    if not reason:
        raise InventoryOperationError("A reversal reason is required.")

    try:
        with transaction.atomic():
            original = (
                StockMovement.objects.select_for_update()
                .select_related("stock_item", "stock_item__project", "stock_item__unit")
                .get(pk=movement.pk)
            )
            if original.movement_type == StockMovement.Type.REVERSAL:
                raise InventoryOperationError("A reversal movement cannot be reversed.")
            if movement_date < original.movement_date:
                raise InventoryOperationError(
                    "Reversal date cannot be earlier than the original movement date."
                )
            if StockMovement.objects.filter(reversal_of=original).exists():
                raise MovementAlreadyReversedError("This movement has already been reversed.")

            stock_item = (
                StockItem.objects.select_for_update()
                .select_related("project", "unit")
                .get(pk=original.stock_item_id)
            )
            _require_active_stock_item(stock_item)
            previous_balance = stock_item.current_quantity
            original_delta = original.new_balance - original.previous_balance
            new_balance = previous_balance - original_delta
            if new_balance < 0:
                raise InsufficientStockError(
                    "This inbound movement cannot be reversed because part of its stock has "
                    "already been used. Add or correct stock before reversing it."
                )

            _save_balance(stock_item=stock_item, new_balance=new_balance, user=user)
            reversal = _create_movement(
                stock_item=stock_item,
                movement_type=StockMovement.Type.REVERSAL,
                quantity=original.quantity,
                previous_balance=previous_balance,
                new_balance=new_balance,
                movement_date=movement_date,
                idempotency_key=idempotency_key,
                user=user,
                unit_price=original.unit_price,
                invoice_reference=original.invoice_reference,
                reason=reason,
                notes=f"Reversal of {original.reference}",
                reversal_of=original,
            )

            if original.movement_type in {
                StockMovement.Type.OPENING,
                StockMovement.Type.ADDITION,
            }:
                latest = _latest_unreversed_addition(stock_item)
                latest_priced = _latest_unreversed_priced_addition(stock_item)
                _save_balance(
                    stock_item=stock_item,
                    new_balance=new_balance,
                    user=user,
                    latest_unit_price=latest_priced.unit_price if latest_priced else None,
                    latest_addition_date=latest.movement_date if latest else None,
                )
            return MovementResult(movement=reversal)
    except IntegrityError:
        duplicate = _existing_idempotent_result(idempotency_key)
        if duplicate:
            return duplicate
        raise


def set_stock_item_status(*, stock_item: StockItem, user, status: str) -> StockItem:
    """Archive/reactivate a zero-balance stock identity without touching movement history."""
    if status not in StockItem.Status.values:
        raise InventoryOperationError("Choose a valid stock-record status.")
    with transaction.atomic():
        locked = (
            StockItem.objects.select_for_update()
            .select_related("project", "unit")
            .get(pk=stock_item.pk)
        )
        if locked.status == status:
            return locked
        if status == StockItem.Status.ARCHIVED:
            if locked.current_quantity != 0:
                raise InventoryOperationError(
                    "A stock record can be archived only when its balance is zero. "
                    "Use or adjust the remaining stock first."
                )
        else:
            if locked.project.status != Project.Status.ACTIVE:
                raise InventoryOperationError(
                    "Reactivate the project before reactivating this stock record."
                )
            if not locked.unit.is_active:
                raise InventoryOperationError(
                    "Reactivate the unit before reactivating this stock record."
                )
        locked.status = status
        locked.updated_by = user
        locked.save(update_fields=["status", "updated_by", "updated_at"])
        return locked
