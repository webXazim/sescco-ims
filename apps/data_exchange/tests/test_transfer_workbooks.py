import io
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from apps.accounts.models import CompanyMembership, MembershipProjectScope, ScopeMode
from apps.accounts.roles import AccessRole
from apps.core.models import AuditEvent
from apps.core.tests.tenant import primary_company
from apps.inventory.models import (
    InventoryLocation,
    StockApprovalRequest,
    StockItem,
    StockTransfer,
    Unit,
)
from apps.inventory.services.approvals import decide_request
from apps.inventory.services.stock import add_stock, use_stock
from apps.projects.models import Project

from ..models import ExportAudit


class TransferWorkbookTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.company = primary_company()
        self.owner = User.objects.create_user(username="excel-owner", password="safe-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=self.owner,
            role=AccessRole.OWNER,
        )
        self.manager1 = User.objects.create_user(username="excel-manager-1")
        self.manager2 = User.objects.create_user(username="excel-manager-2")
        self.p1 = Project.objects.create(company=self.company, code="XLS-SRC", name="Excel Source")
        self.p2 = Project.objects.create(
            company=self.company,
            code="XLS-DST",
            name="Excel Destination",
        )
        self._assign_manager(self.manager1, self.p1)
        self._assign_manager(self.manager2, self.p2)
        self.office = InventoryLocation.objects.for_company(self.company).filter(
            location_type=InventoryLocation.Type.OFFICE,
            deleted_at__isnull=True,
        ).first()
        if self.office is None:
            self.office = InventoryLocation.objects.create(
                company=self.company,
                code="XLS-HQ",
                name="Main Office",
                location_type=InventoryLocation.Type.OFFICE,
            )
        self.unit = Unit.objects.for_company(self.company).get(normalized_name="piece")
        receipt = add_stock(
            user=self.owner,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("10"),
            movement_date=timezone.localdate(),
            project=self.p1,
            material_name="Transfer Cable",
            supplier_name="Excel Supplier",
            supplier_phone="0501234000",
            unit=self.unit,
        ).approval_request
        decide_request(
            request=receipt,
            user=self.manager1,
            project_id=self.p1.pk,
            decision="approve",
        )
        self.item = StockItem.objects.for_company(self.company).get(project=self.p1)
        self.client.force_login(self.owner)

    def _assign_manager(self, user, project):
        membership = CompanyMembership.objects.create(
            company=self.company,
            user=user,
            role=AccessRole.PROJECT_MANAGER,
            project_scope_mode=ScopeMode.SELECTED,
        )
        MembershipProjectScope.objects.create(membership=membership, project=project)

    def _export(self):
        response = self.client.get(
            reverse("data_exchange:transfer_workbook_export", args=[self.p1.inventory_location.pk])
        )
        self.assertEqual(response.status_code, 200)
        return response.content

    def _completed_workbook(self, quantity):
        workbook = load_workbook(io.BytesIO(self._export()))
        workbook["Transfer Lines"]["H2"] = quantity
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()
        return output.getvalue()

    @staticmethod
    def _upload(payload):
        return SimpleUploadedFile(
            "stock-transfer.xlsx",
            payload,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def _post(self, payload, destination):
        return self.client.post(
            reverse("data_exchange:transfer_workbook", args=[self.p1.inventory_location.pk]),
            {
                "source_file": self._upload(payload),
                "destination_location": destination.pk,
                "transfer_date": timezone.localdate().isoformat(),
                "document_reference": "XLS-TRANSFER-1",
            },
        )

    def test_project_destination_queues_one_approval_then_posts(self):
        payload = self._completed_workbook(3)

        response = self._post(payload, self.p2.inventory_location)

        request = StockApprovalRequest.objects.for_company(self.company).get(kind="transfer")
        self.assertRedirects(
            response,
            reverse("inventory:approval_detail", args=[request.reference]),
        )
        self.assertEqual(request.decisions.get().project, self.p2)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("10"))
        self.assertTrue(AuditEvent.objects.filter(
            action="inventory.transfer_workbook.imported",
            object_id=str(request.reference),
            actor=self.owner,
        ).exists())
        self.assertContains(
            self.client.get(reverse("inventory:approval_detail", args=[request.reference])),
            "Excel transfer imported",
        )

        approved = decide_request(
            request=request,
            user=self.owner,
            project_id=self.p2.pk,
            decision="approve",
        )
        self.item.refresh_from_db()
        self.assertEqual(approved.status, StockApprovalRequest.Status.APPROVED)
        self.assertEqual(self.item.current_quantity, Decimal("7"))
        self.assertEqual(
            approved.applied_transfer.lines.get().destination_stock_item.current_quantity,
            Decimal("3"),
        )

    def test_office_destination_posts_immediately(self):
        response = self._post(self._completed_workbook(2), self.office)

        transfer = StockTransfer.objects.for_company(self.company).get()
        self.assertRedirects(
            response,
            reverse("inventory:transfer_detail", args=[transfer.reference]),
        )
        self.assertFalse(
            StockApprovalRequest.objects.for_company(self.company).filter(kind="transfer").exists()
        )
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("8"))
        self.assertEqual(transfer.destination_location, self.office)

    def test_reimporting_same_manifest_is_idempotent(self):
        payload = self._completed_workbook(2)

        self.assertEqual(self._post(payload, self.office).status_code, 302)
        self.assertEqual(self._post(payload, self.office).status_code, 302)

        self.assertEqual(StockTransfer.objects.for_company(self.company).count(), 1)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_quantity, Decimal("8"))
        self.assertEqual(
            AuditEvent.objects.filter(action="inventory.transfer_workbook.imported").count(),
            1,
        )

    def test_stale_source_balance_requires_fresh_export(self):
        payload = self._completed_workbook(2)
        use_stock(
            stock_item=self.item,
            user=self.owner,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("1"),
            movement_date=timezone.localdate(),
            purpose="Balance changed after export",
        )

        response = self._post(payload, self.office)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "source balance changed after export", status_code=400)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_modified_protected_row_is_rejected(self):
        workbook = load_workbook(io.BytesIO(self._export()))
        workbook["Transfer Lines"]["B2"] = "Different material"
        workbook["Transfer Lines"]["H2"] = 1
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()

        response = self._post(output.getvalue(), self.office)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "protected stock fields were changed", status_code=400)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_formula_quantity_is_rejected(self):
        workbook = load_workbook(io.BytesIO(self._export()))
        workbook["Transfer Lines"]["H2"] = "=1+1"
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()

        response = self._post(output.getvalue(), self.office)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "formulas are not allowed", status_code=400)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_sparse_oversized_worksheet_is_rejected(self):
        workbook = load_workbook(io.BytesIO(self._export()))
        workbook["Transfer Lines"]["H5003"] = 1
        output = io.BytesIO()
        workbook.save(output)
        workbook.close()

        response = self._post(output.getvalue(), self.office)

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "at most 5000 stock rows", status_code=400)
        self.assertFalse(StockTransfer.objects.for_company(self.company).exists())

    def test_export_records_manifest_audit(self):
        payload = self._export()
        workbook = load_workbook(io.BytesIO(payload), data_only=True)
        self.assertEqual(
            workbook.sheetnames,
            ["Instructions", "Transfer Lines", "SESCCO Metadata"],
        )
        self.assertEqual(workbook["Transfer Lines"]["A2"].value, str(self.item.reference))
        workbook.close()
        audit = ExportAudit.objects.get(dataset=ExportAudit.Dataset.TRANSFER_WORKSHEET)
        self.assertEqual(audit.row_count, 1)
        self.assertEqual(audit.scope_reference, str(self.p1.inventory_location.reference))

    def test_excel_transfer_entry_points_render(self):
        transfer_url = reverse(
            "data_exchange:transfer_workbook",
            args=[self.p1.inventory_location.pk],
        )
        self.assertContains(self.client.get(transfer_url), "Download fresh worksheet")
        self.assertContains(
            self.client.get(reverse("projects:detail", args=[self.p1.code])),
            transfer_url,
        )
        self.assertContains(
            self.client.get(reverse("inventory:office")),
            "Excel transfer",
        )
