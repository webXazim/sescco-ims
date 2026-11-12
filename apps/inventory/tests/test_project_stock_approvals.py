"""Regression coverage for pending project receipts and two-sided transfer approvals."""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import CompanyMembership, MembershipProjectScope, ScopeMode
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

    def test_missing_manager_blocks_project_receipt(self):
        self.p1.inventory_manager = None
        self.p1.save()
        with self.assertRaises(InventoryOperationError):
            self._add()
        self.assertEqual(StockApprovalRequest.objects.for_company(self.company).count(), 0)

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
