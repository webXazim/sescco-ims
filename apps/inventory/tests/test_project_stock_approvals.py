"""Regression coverage for project receipts and destination transfer approvals."""
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.access_catalog import AccessPermission
from apps.accounts.models import (
    AccessProfile,
    AccessProfilePermission,
    CompanyMembership,
    MembershipProjectScope,
    ScopeMode,
)
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent
from apps.core.tests.tenant import primary_company
from apps.projects.models import Project

from ..access import (
    restrict_inventory_location_queryset,
    restrict_inventory_movements,
    restrict_inventory_stock,
    restrict_inventory_transfers,
)
from ..models import (
    InventoryLocation,
    StockApprovalDecision,
    StockApprovalRequest,
    StockItem,
    StockMovement,
    StockTransfer,
    Unit,
)
from ..services.approvals import can_decide, decide_request
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
        self.assertTrue(can_decide(self.manager1, self.p2))  # explicit permission + All-project scope wins
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

    def test_transfer_between_two_projects_needs_only_destination_manager(self):
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
        self.assertEqual(result.approval_request.decisions.count(), 1)
        self.assertEqual(result.approval_request.decisions.get().project, self.p2)
        with self.assertRaises(InventoryOperationError):
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

    def test_transfer_from_project_to_office_posts_without_approval(self):
        created = self._add()
        self._approve(created.approval_request, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        result = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.office,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, "new", Decimal("1"))],
        )
        self.assertIsNotNone(result.transfer)
        self.assertIsNone(result.approval_request)
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("1"))

    def test_legacy_source_decision_does_not_block_destination_approval(self):
        created = self._add()
        self._approve(created.approval_request, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        request = transfer_stock(
            user=self.requester,
            idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, "new", Decimal("1"))],
        ).approval_request
        StockApprovalDecision.objects.create(
            request=request,
            project=self.p1,
            is_required=False,
        )

        approved = self._approve(request, self.manager2, self.p2)

        self.assertEqual(approved.status, StockApprovalRequest.Status.APPROVED)
        self.assertEqual(
            approved.decisions.get(project=self.p1).status,
            StockApprovalDecision.Status.PENDING,
        )

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

    def test_request_can_wait_for_authorized_approver_without_posting_stock(self):
        outside = Project.objects.create(company=self.company, code="NO-PM", name="No Manager")
        self.assertFalse(can_decide(self.manager1, outside))
        self.assertFalse(can_decide(self.manager2, outside))
        queued = self._add(project=outside).approval_request
        self.assertEqual(queued.status, 'pending')
        self.assertFalse(StockMovement.objects.for_company(self.company).exists())
        self.assertFalse(StockItem.objects.for_company(self.company).filter(project=outside).exists())
        # A later authorized profile can decide the same pending request.
        member = CompanyMembership.objects.get(company=self.company, user=self.manager1)
        MembershipProjectScope.objects.create(membership=member, project=outside)
        self.assertTrue(can_decide(self.manager1, outside))
        self.assertEqual(self._approve(queued, self.manager1, outside).status, 'approved')

    def test_dedicated_assignee_does_not_override_other_permission_holders(self):
        member = CompanyMembership.objects.get(company=self.company, user=self.manager2)
        member.project_scope_mode = ScopeMode.ALL
        member.save(update_fields=("project_scope_mode", "updated_at"))
        self.assertTrue(can_decide(self.manager2, self.p1))
        self.assertTrue(can_decide(self.manager1, self.p1))
        req = self._add().approval_request
        self.assertEqual(self._approve(req, self.manager2, self.p1).status, "approved")

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
        self.assertTrue(can_decide(self.manager1, self.p1))  # the grant is independent of the Pulse assignment
        queued = self._add().approval_request
        self.assertEqual(self._approve(queued, pulse_user, self.p1).status, "approved")

    def test_revoked_pulse_manager_cannot_approve_but_other_authorized_user_can(self):
        from apps.project_pulse.models import PulseProjectTeamMember
        User = get_user_model()
        pulse_user = User.objects.create_user(username="pulse-no-inventory-grant", password="TestPass!2026")
        membership = CompanyMembership.objects.create(company=self.company, user=pulse_user, role=AccessRole.OWNER)
        PulseProjectTeamMember.objects.create(project=self.p1, membership=membership,
                                               role=PulseProjectTeamMember.Role.MANAGER)
        self.p1.inventory_manager = None
        self.p1.save()
        CompanyMembership.objects.filter(pk=membership.pk).update(is_active=False)
        self.assertFalse(can_decide(pulse_user, self.p1))
        self.assertTrue(can_decide(self.manager1, self.p1))
        req = self._add().approval_request
        self.assertEqual(self._approve(req, self.manager1, self.p1).status, "approved")

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

    def _custom_user(self, name, permissions, *, mode=ScopeMode.ALL, projects=()):
        User = get_user_model()
        user = User.objects.create_user(username=name, password="TestPass!2026")
        profile = AccessProfile.objects.create(
            company=self.company, key=f"custom-{name}", name=f"Custom {name}",
        )
        for permission in permissions:
            AccessProfilePermission.objects.create(profile=profile, permission=permission.value)
        membership = CompanyMembership.objects.create(
            company=self.company, user=user, role=AccessRole.CUSTOM,
            access_profile=profile, project_scope_mode=mode,
        )
        for project in projects:
            MembershipProjectScope.objects.create(membership=membership, project=project)
        return user, membership, profile

    def test_custom_profile_approves_without_manager_designation(self):
        user, _, _ = self._custom_user(
            'custom-approver-one', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        self.assertTrue(can_decide(user, self.p1))
        self.assertFalse(can_decide(user, self.p2))
        req = self._add().approval_request
        self.assertEqual(self._approve(req, user, self.p1).status, 'approved')
        self.assertTrue(StockMovement.objects.for_company(self.company).exists())

    def test_custom_profile_can_reject_in_scope(self):
        user, _, _ = self._custom_user(
            'custom-reject', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        req = self._add().approval_request
        rejected = decide_request(
            request=req, user=user, project_id=self.p1.pk,
            decision='reject', reason='Invoice does not match',
        )
        self.assertEqual(rejected.status, 'rejected')
        self.assertFalse(StockMovement.objects.for_company(self.company).exists())

    def test_custom_receive_and_approve_cannot_self_approve(self):
        user, _, _ = self._custom_user(
            'custom-two-grants', [AccessPermission.INVENTORY_STOCK_RECEIVE, AccessPermission.INVENTORY_STOCK_APPROVE],
        )
        req = add_stock(
            user=user, idempotency_key=uuid.uuid4(), movement_date=timezone.localdate(),
            project=self.p1, material_name='Keyboard', supplier_name='Office Supplier',
            supplier_phone='0509000099', unit=self.piece, quantity=Decimal('1'),
        ).approval_request
        self.assertTrue(can_decide(user, self.p1))
        with self.assertRaises(InventoryOperationError):
            self._approve(req, user, self.p1)
        self.assertFalse(StockMovement.objects.for_company(self.company).exists())

    def test_custom_permission_revocation_stops_approval(self):
        user, _, profile = self._custom_user(
            'custom-revoke-approve', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        req = self._add().approval_request
        self.assertTrue(can_decide(user, self.p1))
        AccessProfilePermission.objects.filter(
            profile=profile, permission=AccessPermission.INVENTORY_STOCK_APPROVE.value,
        ).delete()
        self.assertFalse(can_decide(user, self.p1))
        with self.assertRaises(InventoryOperationError):
            self._approve(req, user, self.p1)
        self.assertEqual(req.status, 'pending')
        self.assertFalse(StockMovement.objects.for_company(self.company).exists())

    def test_permission_only_user_can_view_review_and_decide(self):
        from django.urls import reverse
        user, _, _ = self._custom_user(
            'custom-approval-inbox', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        req = self._add().approval_request
        self.client.force_login(user)
        inbox = self.client.get(reverse('inventory:approval_list'))
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, str(req.reference)[:8].upper())
        detail = self.client.get(reverse('inventory:approval_detail', args=[req.reference]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, 'Approve for this project')
        action = self.client.post(reverse('inventory:approval_decide', args=[req.reference]), {
            'project_id': self.p1.pk, 'decision': 'approve',
        })
        self.assertEqual(action.status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'approved')

    def test_receive_only_can_submit_and_see_own_request(self):
        from django.urls import reverse
        # Separate Receive/Approve permissions: receiving is not approval authority.
        user, _, _ = self._custom_user(
            'receive-only-operator', [AccessPermission.INVENTORY_STOCK_RECEIVE],
        )
        req = add_stock(
            user=user, idempotency_key=uuid.uuid4(), movement_date=timezone.localdate(),
            project=self.p1, material_name='Tools', supplier_name='Company supplier',
            supplier_phone='0500000999', unit=self.piece, quantity=Decimal('1'),
        ).approval_request
        self.assertIsNotNone(req)
        self.assertFalse(can_decide(user, self.p1))
        self.client.force_login(user)
        inbox = self.client.get(reverse('inventory:approval_list'))
        self.assertEqual(inbox.status_code, 200)
        self.assertContains(inbox, str(req.reference)[:8].upper())
        self.assertEqual(self.client.get(reverse('inventory:approval_detail', args=[req.reference])).status_code, 200)
        with self.assertRaises(InventoryOperationError):
            self._approve(req, user, self.p1)

    def test_transfers_require_destination_project_decision(self):
        source_user, _, _ = self._custom_user(
            'transfer-source-approver', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        dest_user, _, _ = self._custom_user(
            'transfer-dest-approver', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p2,),
        )
        rec = self._add().approval_request
        self._approve(rec, source_user, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        transfer = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location, destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(), allocations=[TransferAllocation(item, 'new', Decimal('1'))],
        )
        self.assertIsNotNone(transfer.approval_request)
        self.assertEqual(
            list(transfer.approval_request.decisions.values_list('project_id', flat=True)),
            [self.p2.pk],
        )
        with self.assertRaises(InventoryOperationError):
            self._approve(transfer.approval_request, source_user, self.p1)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())
        approved = self._approve(transfer.approval_request, dest_user, self.p2)
        self.assertEqual(approved.status, 'approved')
        self.assertTrue(StockTransfer.objects.for_company(self.company).exists())

    def test_pending_transfer_filter_and_transfer_page_link(self):
        from django.urls import reverse
        receipt = self._add().approval_request
        self._approve(receipt, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        transfer = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location, destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(), allocations=[TransferAllocation(item, 'new', Decimal('1'))],
        ).approval_request
        # A fresh pending receipt should not appear in transfer-only results.
        pending_receipt = self._add(material_name="Unrelated tools").approval_request
        self.client.force_login(self.manager2)
        filtered = self.client.get(reverse("inventory:approval_list"), {"kind": "transfer", "status": "pending"})
        self.assertEqual(filtered.status_code, 200)
        self.assertContains(filtered, str(transfer.reference)[:8].upper())
        self.assertNotContains(filtered, str(pending_receipt.reference)[:8].upper())
        self.assertContains(filtered, "Stock transfers")
        self.assertContains(filtered, "Review")
        self.client.force_login(self.requester)
        history = self.client.get(reverse("inventory:transfer_list"))
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Pending transfer approvals")
        self.assertContains(history, "?status=pending&amp;kind=transfer", html=False)

    def test_approval_list_live_search_sort_and_simplified_columns(self):
        from django.urls import reverse

        self.requester.first_name = "Inventory"
        self.requester.last_name = "Owner"
        self.requester.save(update_fields=("first_name", "last_name"))
        receipt = self._add(material_name="Searchable Cable").approval_request
        self._approve(receipt, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(material_name="Searchable Cable")
        transfer = transfer_stock(
            user=self.requester,
            idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, "new", Decimal("1"))],
        ).approval_request
        later_receipt = self._add(material_name="Unrelated Generator").approval_request
        self.client.force_login(self.requester)
        url = reverse("inventory:approval_list")

        searched = self.client.get(url, {"q": "Searchable Cable"})
        self.assertContains(searched, str(transfer.reference)[:8].upper())
        self.assertNotContains(searched, str(later_receipt.reference)[:8].upper())
        self.assertContains(searched, "data-live-filter-form")
        self.assertContains(searched, "data-live-filter-search")
        self.assertContains(searched, "data-filter-results")
        self.assertNotContains(searched, "Project awaiting action")
        self.assertNotContains(searched, "<th>Submitted</th>", html=True)
        requester_search = self.client.get(url, {"q": "Inventory Owner"})
        self.assertContains(requester_search, str(transfer.reference)[:8].upper())
        self.assertContains(requester_search, str(later_receipt.reference)[:8].upper())

        oldest = self.client.get(url, {"sort": "oldest"})
        newest = self.client.get(url, {"sort": "newest"})
        self.assertEqual(oldest.context["approvals"][0].pk, transfer.pk)
        self.assertEqual(newest.context["approvals"][0].pk, later_receipt.pk)
        by_project = self.client.get(url, {"sort": "project"})
        self.assertEqual(by_project.context["approvals"][0].pk, later_receipt.pk)
        fallback = self.client.get(url, {"sort": "not-a-sort"})
        self.assertEqual(fallback.context["current_sort"], "newest")

    def test_transfer_only_can_submit_without_approval_permission(self):
        # Granting Transfer never grants Approve / Reject.
        user, _, _ = self._custom_user(
            'custom-transfer-only', [AccessPermission.INVENTORY_STOCK_TRANSFER],
        )
        rec = self._add().approval_request
        self._approve(rec, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        result = transfer_stock(
            user=user, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location, destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(), allocations=[TransferAllocation(item, 'new', Decimal('1'))],
        )
        self.assertIsNotNone(result.approval_request)
        self.assertEqual(result.approval_request.status, 'pending')
        self.assertFalse(can_decide(user, self.p2))
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_destination_approval_grant_revocation_blocks_post(self):
        destination_approver, _, profile = self._custom_user(
            'destination-revokable', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p2,),
        )
        rec = self._add().approval_request
        self._approve(rec, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        result = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location, destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(), allocations=[TransferAllocation(item, 'new', Decimal('1'))],
        )
        req = result.approval_request
        AccessProfilePermission.objects.filter(profile=profile, permission=AccessPermission.INVENTORY_STOCK_APPROVE.value).delete()
        with self.assertRaises(InventoryOperationError):
            self._approve(req, destination_approver, self.p2)
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_custom_scope_blocks_other_project_and_other_company(self):
        user, _, _ = self._custom_user(
            'project-selected-reviewer', [AccessPermission.INVENTORY_STOCK_APPROVE],
            mode=ScopeMode.SELECTED, projects=(self.p1,),
        )
        self.assertFalse(can_decide(user, self.p2))
        from apps.core.models import Company
        other = Company.objects.create(name='Another company', slug='another-approval-company')
        outside = Project.objects.create(company=other, code='OTHER-P', name='Other project')
        self.assertFalse(can_decide(user, outside))
        req = self._add(project=self.p2).approval_request
        with self.assertRaises(InventoryOperationError):
            self._approve(req, user, self.p2)

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

    def test_company_owner_can_submit_and_approve_destination_transfer_with_activity(self):
        from django.urls import reverse

        receipt = self._add().approval_request
        self._approve(receipt, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        self.client.force_login(self.requester)
        response = self.client.post(reverse('inventory:transfer_create'), {
            'source_location': self.p1.inventory_location.pk,
            'destination_location': self.p2.inventory_location.pk,
            'idempotency_key': uuid.uuid4(),
            'transfer_date': timezone.localdate().isoformat(),
            f'item_{item.pk}_new': '1',
        })
        self.assertEqual(response.status_code, 302)
        request = StockApprovalRequest.objects.for_company(self.company).filter(kind='transfer').get()
        self.assertEqual(request.requested_by, self.requester)
        self.assertEqual(request.decisions.get().project, self.p2)
        detail_url = reverse('inventory:approval_detail', args=[request.reference])
        detail = self.client.get(detail_url)
        self.assertContains(detail, 'Approve for this project')
        self.assertContains(detail, 'Activity history')

        decision_response = self.client.post(reverse('inventory:approval_decide', args=[request.reference]), {
            'project_id': self.p2.pk,
            'decision': 'approve',
        })
        self.assertRedirects(decision_response, detail_url)
        request.refresh_from_db()
        decision = request.decisions.get()
        self.assertEqual(request.status, StockApprovalRequest.Status.APPROVED)
        self.assertEqual(decision.decided_by, self.requester)
        self.assertIsNotNone(decision.decided_at)
        events = list(AuditEvent.objects.filter(
            company=self.company,
            object_type='inventory.StockApprovalRequest', object_id=str(request.reference),
        ).order_by('created_at'))
        self.assertEqual([event.action for event in events], [
            'inventory.stock_approval.submitted',
            'inventory.stock_approval.approved',
        ])
        self.assertEqual(events[-1].actor, self.requester)
        self.assertIsNotNone(events[-1].created_at)
        detail = self.client.get(detail_url)
        self.assertContains(detail, 'Request approved')
        self.assertContains(detail, self.requester.display_name)

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

    def _pending_project_transfer(self, *, destination=None):
        receipt = self._add().approval_request
        self._approve(receipt, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        transfer = transfer_stock(
            user=self.requester, idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=destination or self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, 'new', Decimal('1'))],
        ).approval_request
        return transfer, item

    def test_requester_can_cancel_pending_transfer_without_stock_movement(self):
        from ..services.approvals import cancel_pending_transfer
        req, item = self._pending_project_transfer()
        before = item.current_quantity
        cancelled = cancel_pending_transfer(
            request=req, user=self.requester, reason='Source material no longer required',
        )
        self.assertEqual(cancelled.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(cancelled.cancelled_by, self.requester)
        self.assertEqual(cancelled.cancellation_reason, 'Source material no longer required')
        self.assertIsNotNone(cancelled.decided_at)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, before)
        with self.assertRaises(InventoryOperationError):
            self._approve(cancelled, self.manager2, self.p2)
        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(request=cancelled, user=self.requester, reason='Again')

    def test_company_owner_can_cancel_another_requesters_pending_transfer(self):
        from django.urls import reverse

        from ..services.approvals import cancel_pending_transfer, pending_visible_request_count

        operator, _, _ = self._custom_user(
            "owner-cancel-operator",
            [AccessPermission.INVENTORY_STOCK_TRANSFER],
        )
        receipt = self._add().approval_request
        self._approve(receipt, self.manager1, self.p1)
        item = StockItem.objects.for_company(self.company).get(project=self.p1)
        request = transfer_stock(
            user=operator,
            idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(item, "new", Decimal("1"))],
        ).approval_request
        owner_membership = CompanyMembership.objects.get(
            company=self.company,
            user=self.requester,
        )
        owner_membership.project_scope_mode = ScopeMode.NONE
        owner_membership.inventory_location_scope_mode = ScopeMode.NONE
        owner_membership.save(
            update_fields=(
                "project_scope_mode",
                "inventory_location_scope_mode",
                "updated_at",
            )
        )
        self.assertEqual(
            pending_visible_request_count(
                company=self.company,
                user=self.requester,
                membership=owner_membership,
            ),
            1,
        )

        self.client.force_login(self.requester)
        list_response = self.client.get(reverse("inventory:approval_list"))
        self.assertContains(list_response, str(request.reference)[:8].upper())
        self.assertContains(list_response, "Cancel")
        detail_url = reverse("inventory:approval_detail", args=[request.reference])
        self.assertContains(self.client.get(detail_url), "Cancel pending transfer")
        response = self.client.post(
            reverse("inventory:approval_cancel", args=[request.reference]),
            {"reason": "Cancelled by company administration"},
        )
        self.assertRedirects(response, detail_url)
        request.refresh_from_db()
        self.assertEqual(request.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(request.cancelled_by, self.requester)
        self.assertTrue(AuditEvent.objects.filter(
            action="inventory.stock_approval.cancelled",
            object_id=str(request.reference),
            actor=self.requester,
        ).exists())

        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(
                request=request,
                user=operator,
                reason="Already cancelled",
            )

    def test_cancellation_requires_original_requester_reason_and_pending_transfer(self):
        from ..services.approvals import cancel_pending_transfer
        req, item = self._pending_project_transfer()
        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(request=req, user=self.manager1, reason='Not mine')
        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(request=req, user=self.requester, reason='  ')
        receipt = self._add(material_name='Another device').approval_request
        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(request=receipt, user=self.requester, reason='Wrong type')
        self.assertEqual(StockApprovalRequest.objects.get(pk=req.pk).status, 'pending')
        self._approve(req, self.manager2, self.p2)
        with self.assertRaises(InventoryOperationError):
            cancel_pending_transfer(request=req, user=self.requester, reason='Already posted')

    def test_cancel_before_destination_approval_preserves_history(self):
        from ..services.approvals import cancel_pending_transfer
        req, item = self._pending_project_transfer(destination=self.p2.inventory_location)
        cancelled = cancel_pending_transfer(request=req, user=self.requester, reason='Change of destination')
        self.assertEqual(cancelled.status, 'cancelled')
        self.assertEqual(cancelled.decisions.get(project=self.p2).status, 'pending')
        with self.assertRaises(InventoryOperationError):
            self._approve(req, self.manager2, self.p2)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal('2'))

    def test_cancel_page_and_pending_sidebar_counter_are_project_scoped(self):
        from django.urls import reverse

        from ..services.approvals import pending_visible_request_count
        req, _item = self._pending_project_transfer(destination=self.p2.inventory_location)
        member1 = CompanyMembership.objects.get(user=self.manager1, company=self.company)
        member2 = CompanyMembership.objects.get(user=self.manager2, company=self.company)
        requester = CompanyMembership.objects.get(user=self.requester, company=self.company)
        self.assertEqual(pending_visible_request_count(company=self.company, user=self.manager1, membership=member1), 0)
        self.assertEqual(pending_visible_request_count(company=self.company, user=self.manager2, membership=member2), 1)
        self.assertEqual(pending_visible_request_count(company=self.company, user=self.requester, membership=requester), 1)
        self.client.force_login(self.requester)
        listing = self.client.get(reverse('inventory:approval_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Pending stock requests visible to you')
        detail_url = reverse('inventory:approval_detail', args=[req.reference])
        cancel_url = reverse('inventory:approval_cancel', args=[req.reference])
        self.assertContains(self.client.get(detail_url), 'Cancel pending transfer')
        self.assertEqual(self.client.get(cancel_url).status_code, 405)
        self.assertEqual(self.client.post(cancel_url, {'reason': 'No longer required'}).status_code, 302)
        req.refresh_from_db()
        self.assertEqual(req.status, 'cancelled')
        self.assertEqual(pending_visible_request_count(company=self.company, user=self.manager2, membership=member2), 0)
        self.assertEqual(pending_visible_request_count(company=self.company, user=self.requester, membership=requester), 0)
        self.assertContains(self.client.get(detail_url), 'No longer required')
        self.assertContains(self.client.get(reverse('inventory:approval_list'), {'status':'cancelled'}), str(req.reference)[:8].upper())
