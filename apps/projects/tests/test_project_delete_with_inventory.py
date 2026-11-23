import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import CompanyMembership, MembershipProjectScope, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent
from apps.core.tests.tenant import primary_company
from apps.inventory.models import StockApprovalRequest, StockItem, StockMovement, Unit
from apps.inventory.services.approvals import decide_request
from apps.inventory.services.stock import add_stock
from apps.inventory.services.transfers import TransferAllocation, transfer_stock
from apps.projects.models import Project
from apps.projects.services import restore_project_trash


class ProjectDeleteWithInventoryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = primary_company()
        self.owner = User.objects.create_user(username="delete-owner", password="safe-password")
        self.owner_membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.owner,
            role=AccessRole.OWNER,
        )
        self.manager1 = User.objects.create_user(username="delete-manager-1")
        self.manager2 = User.objects.create_user(username="delete-manager-2")
        self.p1 = Project.objects.create(company=self.company, code="DEL-SRC", name="Delete Source")
        self.p2 = Project.objects.create(
            company=self.company,
            code="DEL-DST",
            name="Delete Destination",
        )
        self._assign(self.manager1, self.p1)
        self._assign(self.manager2, self.p2)
        unit = Unit.objects.for_company(self.company).get(normalized_name="piece")
        receipt = add_stock(
            user=self.owner,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            movement_date=timezone.localdate(),
            project=self.p1,
            material_name="Protected Cable",
            supplier_name="Protected Supplier",
            supplier_phone="0509999000",
            unit=unit,
        ).approval_request
        decide_request(
            request=receipt,
            user=self.manager1,
            project_id=self.p1.pk,
            decision="approve",
        )
        self.item = StockItem.objects.for_company(self.company).get(project=self.p1)
        self.pending_transfer = transfer_stock(
            user=self.owner,
            idempotency_key=uuid.uuid4(),
            source_location=self.p1.inventory_location,
            destination_location=self.p2.inventory_location,
            transfer_date=timezone.localdate(),
            allocations=[TransferAllocation(self.item, "new", Decimal("2"))],
        ).approval_request
        self.pending_receipt = add_stock(
            user=self.owner,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("1"),
            movement_date=timezone.localdate(),
            project=self.p1,
            material_name="Pending Tool",
            supplier_name="Pending Supplier",
            supplier_phone="0509999001",
            unit=unit,
        ).approval_request
        self.client.force_login(self.owner)

    def _assign(self, user, project):
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.PROJECT_MANAGER,
            project_scope_mode=ScopeMode.SELECTED,
        )
        MembershipProjectScope.objects.create(membership=membership, project=project)

    def test_owner_deletes_and_restores_project_with_stock_and_pending_transfer(self):
        movement_count = StockMovement.objects.for_company(self.company).count()

        response = self.client.post(
            reverse("projects:delete", args=[self.p1.code]),
            {"reason": "Project cancelled"},
        )

        self.assertRedirects(response, reverse("projects:list"))
        self.p1.refresh_from_db()
        self.item.refresh_from_db()
        location = self.p1.inventory_location
        location.refresh_from_db()
        self.pending_transfer.refresh_from_db()
        self.pending_receipt.refresh_from_db()
        self.assertIsNotNone(self.p1.deleted_at)
        self.assertEqual(self.item.deleted_at, self.p1.deleted_at)
        self.assertEqual(location.deleted_at, self.p1.deleted_at)
        self.assertEqual(self.item.current_quantity, Decimal("5"))
        self.assertEqual(self.pending_transfer.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(self.pending_receipt.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(self.pending_transfer.cancelled_by, self.owner)
        self.assertEqual(
            StockMovement.objects.for_company(self.company).count(),
            movement_count,
        )
        self.assertTrue(AuditEvent.objects.filter(
            action="project.moved_to_trash",
            object_id=str(self.p1.pk),
            actor=self.owner,
        ).exists())
        self.assertTrue(AuditEvent.objects.filter(
            action="inventory.stock_approval.cancelled",
            object_id=str(self.pending_transfer.reference),
            actor=self.owner,
        ).exists())

        restore_project_trash(
            actor_membership=self.owner_membership,
            project_id=self.p1.pk,
        )
        self.p1.refresh_from_db()
        self.item.refresh_from_db()
        location.refresh_from_db()
        self.assertIsNone(self.p1.deleted_at)
        self.assertIsNone(self.item.deleted_at)
        self.assertIsNone(location.deleted_at)
        self.assertEqual(self.item.current_quantity, Decimal("5"))
        self.pending_transfer.refresh_from_db()
        self.pending_receipt.refresh_from_db()
        self.assertEqual(self.pending_transfer.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(self.pending_receipt.status, StockApprovalRequest.Status.CANCELLED)

    def test_django_admin_uses_safe_trash_action_for_project_with_stock(self):
        User = get_user_model()
        admin = User.objects.create_superuser(
            username="safe-project-admin",
            email="safe-project-admin@example.test",
            password="safe-password",
        )
        CompanyMembership.objects.create(
            company=self.company,
            user=admin,
            role=AccessRole.OWNER,
        )
        self.client.force_login(admin)

        delete_url = reverse("admin:projects_project_delete", args=[self.p1.pk])
        self.assertEqual(self.client.get(delete_url).status_code, 403)
        response = self.client.post(
            reverse("admin:projects_project_changelist"),
            {
                "action": "move_selected_projects_to_trash",
                "_selected_action": [self.p1.pk],
            },
        )

        self.assertRedirects(response, reverse("admin:projects_project_changelist"))
        self.p1.refresh_from_db()
        self.item.refresh_from_db()
        self.pending_transfer.refresh_from_db()
        self.pending_receipt.refresh_from_db()
        self.assertIsNotNone(self.p1.deleted_at)
        self.assertEqual(self.item.deleted_at, self.p1.deleted_at)
        self.assertEqual(self.item.current_quantity, Decimal("5"))
        self.assertEqual(self.pending_transfer.status, StockApprovalRequest.Status.CANCELLED)
        self.assertEqual(self.pending_receipt.status, StockApprovalRequest.Status.CANCELLED)
        self.assertTrue(AuditEvent.objects.filter(
            action="project.moved_to_trash",
            object_id=str(self.p1.pk),
            actor=admin,
        ).exists())
