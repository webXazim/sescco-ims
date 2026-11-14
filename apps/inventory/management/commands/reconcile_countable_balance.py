"""Explicit, audited correction for physically counted legacy fractional stock.

Never run automatically during deployment. Does not rewrite any old movements.
Requires an operator-selected whole target, reason and explicit --apply.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.core.models import AuditArea
from apps.core.services.audit import record_audit_event
from apps.inventory.models import StockItem, StockMovement
from apps.accounts.permissions import user_membership_for_company
from apps.accounts.access_catalog import AccessPermission
from apps.accounts.access_policy import membership_has_permission
from apps.inventory.access import location_in_inventory_scope
from apps.inventory.quantity_policy import is_whole
from apps.inventory.services.stock import _create_movement, _save_balance


class Command(BaseCommand):
    help = "Preview or record an audited integer-balance correction for ONE legacy fractional countable stock item."

    def add_arguments(self, parser):
        parser.add_argument("--reference", required=True, help="The stock item's UUID reference")
        parser.add_argument("--target", required=True, help="Physically verified whole-number quantity")
        parser.add_argument("--reason", required=True, help="Reason including physical count evidence / reference")
        parser.add_argument("--actor-username", help="Active Inventory adjust-authorized username, required for --apply")
        parser.add_argument("--apply", action="store_true", help="Write immutable adjustment and update balance")
        parser.add_argument("--confirm-reference", help="Required on --apply, must equal --reference")

    def handle(self, *args, **options):
        try:
            target = Decimal(options["target"])
        except InvalidOperation as exc:
            raise CommandError("Invalid target number.") from exc
        if not is_whole(target) or target < 0:
            raise CommandError("Choose a nonnegative WHOLE stock quantity.")
        reason = options["reason"].strip()
        if not reason or len(reason) > 160:
            raise CommandError("Supply a physical-count reason of 1–160 characters.")
        if options["apply"] and options["confirm_reference"] != options["reference"]:
            raise CommandError("--apply requires --confirm-reference equal to --reference.")
        if options["apply"] and not options["actor_username"]:
            raise CommandError("--apply requires --actor-username for accountability.")
        with transaction.atomic():
            try:
                item = (StockItem.objects.select_for_update().select_related("unit", "project", "location", "company")
                        .get(reference=options["reference"]))
            except (StockItem.DoesNotExist, ValueError) as exc:
                raise CommandError("Stock reference was not found.") from exc
            if item.unit.permits_fractional_quantity:
                raise CommandError("This is a measurable unit; use normal inventory adjustments.")
            if not item.current_quantity % 1:
                raise CommandError("Balance is already whole. Use normal Inventory for any adjustment.")
            if item.deleted_at or item.status != StockItem.Status.ACTIVE or not item.location.accepts_stock_activity:
                raise CommandError("Only active stock at an active location can be reconciled.")
            old = item.current_quantity
            delta = target - old
            if abs(delta) >= Decimal("1"):
                raise CommandError("Target differs by >=1 unit. Only fractional residue correction is allowed.")
            self.stdout.write(f"Company {item.company_id}; {item.location.code}; {item.material_name}: {old} -> {target} {item.unit.symbol}; change {delta:+}; reason {reason}")
            if not options["apply"]:
                self.stdout.write("DRY RUN. Verify the physical count; rerun with --apply and --confirm-reference.")
                return
            actor = get_user_model().objects.filter(username=options["actor_username"], is_active=True).first()
            if not actor:
                raise CommandError("Active actor was not found.")
            membership = user_membership_for_company(actor, item.company)
            if not (membership and membership_has_permission(membership, AccessPermission.INVENTORY_STOCK_ADJUST)
                    and location_in_inventory_scope(membership, item.location)):
                raise CommandError("Actor must have Stock/Adjust permission and access to this stock location.")
            movement = _create_movement(
                stock_item=item,
                movement_type=(StockMovement.Type.ADJUSTMENT_IN if delta > 0 else StockMovement.Type.ADJUSTMENT_OUT),
                quantity=abs(delta), previous_balance=old, new_balance=target,
                movement_date=timezone.localdate(), idempotency_key=uuid4(), user=actor,
                reason=f"Legacy countable fractional reconciliation: {reason}",
                notes="Exceptional admin reconciliation after physical verification; historical movements untouched.",
            )
            _save_balance(stock_item=item, new_balance=target, user=actor)
            record_audit_event(
                company=item.company, area=AuditArea.INVENTORY, actor=actor, actor_membership=membership,
                action="inventory.legacy_quantity.reconciled", object_type="inventory.StockItem",
                object_id=item.reference, object_label=item.material_name,
                before={"quantity": str(old)}, after={"quantity": str(target), "movement": str(movement.reference)},
                metadata={"reason": reason, "command": "reconcile_countable_balance"},
            )
            self.stdout.write(self.style.SUCCESS(f"Recorded movement {movement.reference}; balance now {target}."))
