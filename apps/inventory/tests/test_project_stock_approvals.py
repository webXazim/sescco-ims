"""Regression coverage for pending project receipts and two-sided transfer approvals."""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, MembershipProjectScope, ScopeMode
from ..access import (restrict_inventory_location_queryset, restrict_inventory_stock,
                      restrict_inventory_movements, restrict_inventory_transfers)
from ..services.approvals import can_decide
from apps.accounts.roles import AccessRole
from apps.core.tests.tenant import primary_company
from apps.projects.models import Project
from ..models import InventoryLocation, StockApprovalRequest, StockItem, StockMovement, StockTransfer, Unit
from ..services.approvals import decide_request
from ..services.stock import InventoryOperationError, add_stock
from ..services.transfers import TransferAllocation, transfer_stock


class ProjectApprovalsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = primary_company()
        self.requester = User.objects.create_user(username="inventory-requester", password="TestPass!2026")
        CompanyMembership.objects.create(company=self.company, user=self.requester, role=AccessRole.OWNER)
        self.manager1 = User.objects.create_user(username="manager-alpha", password="TestPass!2026")
        self.manager2 = User.objects.create_user(username="manager-beta", password="TestPass!2026")
        self.p1 = Project.objects.create(company=self.company, code="PM-A", name="Site A")
        self.p2 = Project.objects.create(company=self.company, code="PM-B", name="Site B")
        self._assign(self.p1, self.manager1)
        self._assign(self.p2, self.manager2)
        self.office = InventoryLocation.objects.for_company(self.company).filter(location_type="office").first()
        if self.office is None:
            self.office = InventoryLocation.objects.create(company=self.company, code="HQ-TEST", name="Head office", location_type="office")
        self.piece = Unit.objects.for_company(self.company).get(normalized_name="piece")
        self.kg = Unit.objects.for_company(self.company).get(normalized_name="kilogram")

    def _assign(self, project, user):
        m = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.PROJECT_MANAGER,
            project_scope_mode=ScopeMode.SELECTED,
        )
        MembershipProjectScope.objects.create(membership=m, project=project)
        project.inventory_manager = user
        project.save()

    def _add(self, *, project=None, quantity="2", key=None, unit=None, material_name="Laptop"):
        return add_stock(
            user=self.requester, idempotency_key=key or uuid.uuid4(),
            movement_date=timezone.localdate(), project=project or self.p1,
            material_name=material_name, supplier_name="Office Supplier", supplier_phone="0501234567",
            unit=unit or self.piece, quantity=Decimal(quantity),
        )

    def _approve(self, req, user, project):
        return decide_request(request=req, user=user, project_id=project.pk, decision="approve")

    def test_all_project_scope_grants_project_inventory_visibility_but_not_office_inventory(self):
        member = CompanyMembership.objects.get(company=self.company, user=self.manager1)
        member.project_scope_mode = ScopeMode.ALL
        member.save(update_fields=("project_scope_mode", "updated_at"))
        member.project_scopes.all().delete()
        self.assertTrue(restrict_inventory_location_queryset(
            InventoryLocation.objects.for_company(self.company), member
        ).filter(project=self.p1).exists())
        self.assertTrue(restrict_inventory_location_queryset(
            InventoryLocation.objects.for_company(self.company), member
        ).filter(project=self.p2).exists())
        self.assertFalse(restrict_inventory_location_queryset(
            InventoryLocation.objects.for_company(self.company), member
        ).filter(pk=self.office.pk).exists())
        self.assertFalse(restrict_inventory_stock(
            StockItem.objects.for_company(self.company), member
        ).filter(project__isnull=True).exists())
        self.assertFalse(restrict_inventory_movements(
            StockMovement.objects.for_company(self.company), member
        ).filter(stock_item__project__isnull=True).exists())
        self.assertFalse(restrict_inventory_transfers(
            StockTransfer.objects.for_company(self.company), member
        ).filter(source_location__project__isnull=True, destination_location__project__isnull=True).exists())

    def test_all_project_scope_can_approve_when_no_dedicated_inventory_approver(self):
        member = CompanyMembership.objects.get(company=self.company, user=self.manager1)
        member.project_scope_mode = ScopeMode.ALL
        member.save(update_fields=("project_scope_mode", "updated_at"))
        member.project_scopes.all().delete()
        self.assertFalse(can_decide(self.manager1, self.p2))  # dedicated approver still wins
        self.p2.inventory_manager = None
        self.p2.save()
        self.assertTrue(can_decide(self.manager1, self.p1))
        self.assertTrue(can_decide(self.manager1, self.p2))
        receipt = self._add(project=self.p2)
        self.assertIsNotNone(receipt.approval_request)
        approved = self._approve(receipt.approval_request, self.manager1, self.p2)
        self.assertEqual(approved.status, "approved")
        self.assertTrue(restrict_inventory_stock(
            StockItem.objects.for_company(self.company), member
        ).filter(project=self.p2).exists())
        self.assertTrue(restrict_inventory_movements(
            StockMovement.objects.for_company(self.company), member
        ).filter(stock_item__project=self.p2).exists())

    def test_receipt_waits_without_stock_until_assigned_manager_approves(self):
        result = self._add()
        self.assertIsNone(result.movement)
        self.assertEqual(result.approval_request.status, "pending")
        self.assertFalse(StockItem.objects.for_company(self.company).filter(project=self.p1).exists())
        self.assertEqual(StockMovement.objects.for_company(self.company).count(), 0)
        done = self._approve(result.approval_request, self.manager1, self.p1)
        self.assertEqual(done.status, "approved")
        self.assertEqual(done.applied_movement.quantity, Decimal("2"))
        self.assertEqual(done.applied_movement.stock_item.current_quantity, Decimal("2"))
        with self.assertRaises(InventoryOperationError):
            self._approve(result.approval_request, self.manager1, self.p1)

    def test_cannot_approve_another_projects_request(self):
        req = self._add().approval_request
        with self.assertRaises(InventoryOperationError):
            self._approve(req, self.manager2, self.p1)
        self.assertEqual(StockMovement.objects.for_company(self.company).count(), 0)

    def test_same_request_idempotency_key_does_not_duplicate_pending_or_stock(self):
        key = uuid.uuid4()
        first = self._add(key=key)
        second = self._add(key=key)
        self.assertTrue(second.duplicate_submission)
        self.assertEqual(first.approval_request.pk, second.approval_request.pk)
        self.assertEqual(StockApprovalRequest.objects.for_company(self.company).count(), 1)
        self._approve(first.approval_request, self.manager1, self.p1)
        self.assertEqual(StockMovement.objects.for_company(self.company).count(), 1)

    def test_reject_keeps_stock_unchanged(self):
        req = self._add().approval_request
        result = decide_request(request=req, user=self.manager1, project_id=self.p1.pk, decision="reject", reason="Not received on site")
        self.assertEqual(result.status, "rejected")
        self.assertEqual(StockMovement.objects.for_company(self.company).count(), 0)

    def test_transfer_between_two_projects_needs_both_managers(self):
        created = self._add()
        self._approve(created.approval_request, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        result = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, "new", Decimal("1"))],
        )
        self.assertIsNone(result.transfer)
        self.assertEqual(result.approval_request.decisions.count(), 2)
        self._approve(result.approval_request, self.manager1, self.p1)
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("2"))
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())
        done = self._approve(result.approval_request, self.manager2, self.p2)
        item.refresh_from_db()
        self.assertEqual(done.status, "approved")
        self.assertEqual(item.current_quantity, Decimal("1"))
        self.assertEqual(done.applied_transfer.lines.count(), 1)
        self.assertEqual(done.applied_transfer.lines.get().destination_stock_item.current_quantity, Decimal("1"))

    def test_fallback_to_scoped_project_manager_with_no_inventory_assignee(self):
        self.p1.inventory_manager = None
        self.p1.save()
        self.assertTrue(can_decide(self.manager1, self.p1))
        self.assertFalse(can_decide(self.manager2, self.p1))
        queued = self._add()
        self.assertIsNotNone(queued.approval_request)
        self.assertFalse(StockMovement.objects.for_company(self.company).exists())
        with self.assertRaises(InventoryOperationError):
            self._approve(queued.approval_request, self.manager2, self.p1)
        result = self._approve(queued.approval_request, self.manager1, self.p1)
        self.assertEqual(result.status, "approved")

    def test_no_eligible_project_manager_blocks_before_stock_posting(self):
        outside = Project.objects.create(company=self.company, code="NO-PM", name="No Manager")
        self.assertFalse(can_decide(self.manager1, outside))
        self.assertFalse(can_decide(self.manager2, outside))
        with self.assertRaises(InventoryOperationError):
            self._add(project=outside)
        self.assertEqual(StockApprovalRequest.objects.for_company(self.company).count(), 0)

    def test_dedicated_inventory_approver_overrides_all_scoped_project_manager(self):
        member = CompanyMembership.objects.get(company=self.company, user=self.manager2)
        member.project_scope_mode = ScopeMode.ALL
        member.save(update_fields=("project_scope_mode", "updated_at"))
        self.assertFalse(can_decide(self.manager2, self.p1))
        self.assertTrue(can_decide(self.manager1, self.p1))
        request = self._add().approval_request
        with self.assertRaises(InventoryOperationError):
            self._approve(request, self.manager2, self.p1)
        self.assertEqual(self._approve(request, self.manager1, self.p1).status, "approved")

    def test_pulse_project_manager_can_approve_when_explicit_inventory_assignee_empty(self):
        from apps.project_pulse.models import PulseProjectTeamMember
        User = get_user_model()
        pulse_user = User.objects.create_user(username="pulse-approval-manager", password="TestPass!2026")
        membership = CompanyMembership.objects.create(company=self.company, user=pulse_user, role=AccessRole.OWNER)
        PulseProjectTeamMember.objects.create(
            project=self.p1, membership=membership,
            role=PulseProjectTeamMember.Role.MANAGER,
        )
        self.p1.inventory_manager = None
        self.p1.save()
        self.assertTrue(can_decide(pulse_user, self.p1))
        self.assertFalse(can_decide(self.manager1, self.p1))  # Pulse manager has precedence
        queued = self._add().approval_request
        self.assertEqual(self._approve(queued, pulse_user, self.p1).status, "approved")

    def test_revoking_pulse_manager_approval_fails_closed(self):
        from apps.project_pulse.models import PulseProjectTeamMember
        User = get_user_model()
        pulse_user = User.objects.create_user(username="pulse-no-inventory-grant", password="TestPass!2026")
        membership = CompanyMembership.objects.create(company=self.company, user=pulse_user, role=AccessRole.OWNER)
        PulseProjectTeamMember.objects.create(project=self.p1, membership=membership,
                                               role=PulseProjectTeamMember.Role.MANAGER)
        self.p1.inventory_manager = None
        self.p1.save()
        # This project's appointed manager loses access. An otherwise eligible
        # built-in manager must not override the explicit Pulse assignment.
        CompanyMembership.objects.filter(pk=membership.pk).update(is_active=False)
        self.assertFalse(can_decide(pulse_user, self.p1))
        self.assertFalse(can_decide(self.manager1, self.p1))
        with self.assertRaises(InventoryOperationError):
            self._add()

    def test_fallback_project_manager_approvals_visible_in_inbox(self):
        from django.urls import reverse
        self.p1.inventory_manager = None
        self.p1.save()
        result = self._add()
        self.client.force_login(self.manager1)
        inbox = self.client.get(reverse("inventory:approval_list"))
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, str(result.approval_request.reference)[:8].upper())
        self.client.force_login(self.manager2)
        inbox = self.client.get(reverse("inventory:approval_list"))
        self.assertEqual(inbox.status_code, 200)
        self.assertNotContains(inbox, str(result.approval_request.reference)[:8].upper())

    def test_all_scoped_project_manager_can_approve_new_company_project(self):
        member = CompanyMembership.objects.get(company=self.company, user=self.manager1)
        member.project_scope_mode = ScopeMode.ALL
        member.save(update_fields=("project_scope_mode", "updated_at"))
        new_project = Project.objects.create(company=self.company, code="PM-FUTURE", name="Future project")
        self.assertTrue(can_decide(self.manager1, new_project))
        pending = self._add(project=new_project).approval_request
        self.assertEqual(self._approve(pending, self.manager1, new_project).status, "approved")

    def test_counted_laptops_cannot_have_fractional_quantities(self):
        self.assertFalse(self.piece.allows_fractional_quantities)
        with self.assertRaises(InventoryOperationError):
            self._add(quantity="1.99")
        self.assertEqual(StockApprovalRequest.objects.for_company(self.company).count(), 0)
        self.assertTrue(self.kg.allows_fractional_quantities)
        result = self._add(quantity="1.99", unit=self.kg, material_name="Gravel by weight")
        self.assertIsNotNone(result.approval_request)

    def test_manager_cannot_approve_own_submission(self):
        # Even custom roles with both stock receive and approval grants must be
        # separate from the original request submitter.
        req = self._add().approval_request
        req.requested_by = self.manager1
        req.save(update_fields=("requested_by",))
        with self.assertRaises(InventoryOperationError):
            self._approve(req, self.manager1, self.p1)

    # Regression: legacy migration 0019 could leave countable units decimal-enabled.

    def test_legacy_piece_flag_cannot_reenable_decimal_receipts(self):
        Unit.objects.filter(pk=self.piece.pk).update(allows_fractional_quantities=True)
        self.piece.refresh_from_db()
        self.assertFalse(self.piece.permits_fractional_quantity)
        with self.assertRaises(InventoryOperationError):
            self._add(quantity="0.999")
        with self.assertRaises(InventoryOperationError):
            self._add(quantity="1.5")
        self.assertEqual(StockApprovalRequest.objects.for_company(self.company).count(), 0)

    def test_legacy_piece_flag_blocks_fractional_minimums_and_transfers(self):
        Unit.objects.filter(pk=self.piece.pk).update(allows_fractional_quantities=True)
        self.piece.refresh_from_db()
        with self.assertRaises(InventoryOperationError):
            add_stock(
                user=self.requester, idempotency_key=uuid.uuid4(), project=self.p1,
                movement_date=timezone.localdate(), quantity=Decimal("2"), minimum_quantity=Decimal("0.5"),
                material_name="Counted Device", supplier_name="Supply", supplier_phone="0509000100", unit=self.piece,
            )
        receipt = self._add(quantity="2")
        self._approve(receipt.approval_request, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        with self.assertRaises(InventoryOperationError):
            transfer_stock(
                user=self.requester, idempotency_key=uuid.uuid4(),
                source_location=self.p1.inventory_location, destination_location=self.p2.inventory_location,
                transfer_date=timezone.localdate(),
                allocations=[TransferAllocation(item, "new", Decimal("0.5"))],
            )
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("2"))

    def test_measured_kg_still_allows_decimal_stock(self):
        self.assertTrue(self.kg.permits_fractional_quantity)
        result = self._add(quantity="0.999", unit=self.kg, material_name="Paint powder")
        self.assertIsNotNone(result.approval_request)
