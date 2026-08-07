import tempfile
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.inventory.models import StockItem, StockMovement, Supplier, Unit
from apps.inventory.services.stock import add_stock
from apps.projects.models import Project

User = get_user_model()


class InventoryWorkspaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-password",
        )
        self.client.force_login(self.user)
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.unit = Unit.objects.get(normalized_name="bag")
        self.supplier = Supplier.objects.create(
            name="Gulf Cement",
            phone="+966 57 368 6575",
            location="Dammam",
        )
        self.today = timezone.localdate()

    def create_item(self):
        return StockItem.objects.create(
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
        )

    def add_item_stock(self, quantity="50"):
        return add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal(quantity),
            movement_date=self.today,
            project=self.project,
            material_name="Portland Cement",
            description="50 KG bag",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            supplier_location="Dammam",
            unit=self.unit,
            minimum_quantity=Decimal("10"),
            unit_price=Decimal("24.50"),
            invoice_reference="INV-100",
        )

    def test_legacy_new_stock_url_redirects_to_add_stock(self):
        response = self.client.get(
            reverse("inventory:create"),
            {"project": self.project.code},
        )
        self.assertRedirects(
            response,
            f"{reverse('core:add_stock')}?project={self.project.code}",
            fetch_redirect_response=False,
        )
        self.assertEqual(StockItem.objects.count(), 0)

    def test_stock_identity_edit_cannot_collide_with_existing_record(self):
        existing = self.create_item()
        second = StockItem.objects.create(
            project=self.project,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 000 0000",
            unit=self.unit,
        )
        response = self.client.post(
            reverse("inventory:edit", kwargs={"reference": second.reference}),
            {
                "project": self.project.pk,
                "material_name": existing.material_name,
                "description": "",
                "supplier_name": existing.supplier_name,
                "supplier_phone": existing.supplier_phone,
                "supplier_location": "",
                "unit": self.unit.pk,
                "minimum_quantity": "0",
                "notes": "",
                "status": StockItem.Status.ACTIVE,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "exact stock record already exists")
        second.refresh_from_db()
        self.assertEqual(second.material_name, "Steel Bar")

    def test_similar_identity_edit_requires_confirmation(self):
        self.create_item()
        second = StockItem.objects.create(
            project=self.project,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 000 0000",
            unit=self.unit,
        )
        payload = {
            "project": self.project.pk,
            "material_name": "Portland Cement",
            "description": "",
            "supplier_name": "Gulf Cement",
            "supplier_phone": "+966 55 000 0000",
            "supplier_location": "",
            "unit": self.unit.pk,
            "minimum_quantity": "0",
            "notes": "",
            "status": StockItem.Status.ACTIVE,
        }
        url = reverse("inventory:edit", kwargs={"reference": second.reference})
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "different phone number")

        payload["confirm_similar"] = "on"
        response = self.client.post(url, payload)
        self.assertEqual(response.status_code, 302)
        second.refresh_from_db()
        self.assertEqual(second.material_name, "Portland Cement")
        self.assertEqual(StockItem.objects.count(), 2)

    def test_add_stock_page_creates_new_record_and_movement(self):
        response = self.client.post(
            reverse("core:add_stock"),
            {
                "idempotency_key": uuid.uuid4(),
                "project": self.project.pk,
                "material_name": "Portland Cement",
                "supplier": self.supplier.pk,
                "unit": self.unit.pk,
                "minimum_quantity": "10",
                "quantity": "50",
                "unit_price": "24.50",
                "movement_date": self.today.isoformat(),
                "invoice_reference": "INV-100",
                "notes": "Delivery",
            },
        )
        item = StockItem.objects.get()
        self.assertRedirects(
            response,
            reverse("inventory:detail", kwargs={"reference": item.reference}),
        )
        self.assertEqual(item.current_quantity, Decimal("50"))
        self.assertEqual(item.movements.count(), 1)
        self.assertEqual(item.supplier_name, self.supplier.name)
        self.assertEqual(item.supplier_phone, self.supplier.phone)
        self.assertEqual(item.supplier_location, self.supplier.location)

    def test_add_stock_duplicate_post_is_idempotent(self):
        token = uuid.uuid4()
        payload = {
            "idempotency_key": token,
            "project": self.project.pk,
            "material_name": "Portland Cement",
            "supplier": self.supplier.pk,
            "unit": self.unit.pk,
            "minimum_quantity": "10",
            "quantity": "50",
            "unit_price": "24.50",
            "movement_date": self.today.isoformat(),
            "invoice_reference": "INV-100",
            "notes": "Delivery",
        }
        self.client.post(reverse("core:add_stock"), payload)
        self.client.post(reverse("core:add_stock"), payload)
        item = StockItem.objects.get()
        self.assertEqual(item.current_quantity, Decimal("50"))
        self.assertEqual(StockMovement.objects.count(), 1)

    def test_supplier_can_be_created_and_selected_for_stock(self):
        response = self.client.post(
            reverse("inventory:suppliers"),
            {
                "name": "Eastern Steel",
                "phone": "+966 50 123 4567",
                "location": "Dammam",
                "notes": "Preferred steel vendor",
                "is_active": "on",
            },
        )
        self.assertRedirects(response, reverse("inventory:suppliers"))
        supplier = Supplier.objects.get(normalized_name="eastern steel")
        self.assertEqual(supplier.normalized_phone, "966501234567")

        response = self.client.get(reverse("core:add_stock"))
        self.assertContains(response, "Eastern Steel")
        self.assertNotContains(response, 'id="id_description"')

    def test_use_stock_page_blocks_negative_stock(self):
        item = self.add_item_stock("10").movement.stock_item
        response = self.client.post(
            reverse("core:remove_stock"),
            {
                "idempotency_key": uuid.uuid4(),
                "project": self.project.pk,
                "stock_item": item.pk,
                "quantity": "11",
                "movement_date": self.today.isoformat(),
                "purpose": "Site work",
                "recipient": "Team A",
                "invoice_reference": "USE-1",
                "notes": "",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "Only 10 bag is currently available", status_code=400)
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("10"))

    def test_adjustment_page_records_history(self):
        item = self.add_item_stock("10").movement.stock_item
        response = self.client.post(
            reverse("inventory:adjust", kwargs={"reference": item.reference}),
            {
                "idempotency_key": uuid.uuid4(),
                "direction": "increase",
                "quantity": "2",
                "movement_date": self.today.isoformat(),
                "reason": "Physical count correction",
                "invoice_reference": "COUNT-1",
                "notes": "",
            },
        )
        self.assertRedirects(
            response,
            reverse("inventory:detail", kwargs={"reference": item.reference}),
        )
        item.refresh_from_db()
        self.assertEqual(item.current_quantity, Decimal("12"))
        self.assertEqual(item.movements.count(), 2)

    def test_storekeeper_cannot_reverse_but_admin_can(self):
        movement = self.add_item_stock().movement
        reversal_url = reverse(
            "inventory:movement_reverse",
            kwargs={"reference": movement.reference},
        )
        self.assertEqual(self.client.get(reversal_url).status_code, 403)

        self.client.force_login(self.admin)
        response = self.client.post(
            reversal_url,
            {
                "idempotency_key": uuid.uuid4(),
                "movement_date": self.today.isoformat(),
                "reason": "Duplicate entry",
            },
        )
        self.assertEqual(response.status_code, 302)
        movement.stock_item.refresh_from_db()
        self.assertEqual(movement.stock_item.current_quantity, Decimal("0"))

    def test_inventory_list_filters_by_project_and_search(self):
        self.create_item()
        other = Project.objects.create(code="NEOM-04", name="NEOM Site Works")
        StockItem.objects.create(
            project=other,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 000 0000",
            unit=self.unit,
        )
        response = self.client.get(
            reverse("inventory:list"),
            {"project": self.project.code, "q": "cement"},
        )
        self.assertContains(response, "Portland Cement")
        self.assertNotContains(response, "Steel Bar")

    def test_inventory_search_matches_normalized_phone_digits(self):
        self.create_item()
        response = self.client.get(reverse("inventory:list"), {"q": "966573686575"})
        self.assertContains(response, "Portland Cement")

    def test_activity_filters_by_action_and_date(self):
        movement = self.add_item_stock().movement
        response = self.client.get(
            reverse("core:activity"),
            {
                "movement_type": StockMovement.Type.ADDITION,
                "date_from": self.today.isoformat(),
                "date_to": self.today.isoformat(),
            },
        )
        self.assertContains(response, movement.stock_item.material_name)
        response = self.client.get(
            reverse("core:activity"),
            {"movement_type": StockMovement.Type.USAGE},
        )
        self.assertNotContains(response, movement.stock_item.material_name)

    def test_activity_keeps_historical_project_tag_but_links_current_project(self):
        self.add_item_stock()
        self.project.code = "ARAMCO-UPDATED"
        self.project.save()

        response = self.client.get(reverse("core:activity"))
        self.assertContains(response, "ARAMCO-01")
        self.assertContains(
            response,
            reverse("projects:detail", args=[self.project.code]),
        )

    def test_activity_search_keeps_historical_supplier_phone_identity(self):
        movement = self.add_item_stock().movement
        item = movement.stock_item
        item.supplier_phone = "+966 50 999 9999"
        item.save()

        response = self.client.get(
            reverse("core:activity"),
            {"q": "966573686575"},
        )
        self.assertContains(response, "Portland Cement")

    def test_match_endpoint_requires_all_identity_fields(self):
        response = self.client.get(reverse("inventory:matches"), {"project": self.project.code})
        self.assertEqual(response.status_code, 400)

    def test_stock_picker_filters_by_project_and_search(self):
        item = self.add_item_stock("10").movement.stock_item
        other_project = Project.objects.create(code="NEOM-04", name="NEOM Site Works")
        add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("4"),
            movement_date=self.today,
            project=other_project,
            material_name="Steel Bar",
            supplier_name="Metal Supplier",
            supplier_phone="+966 50 100 2000",
            unit=self.unit,
        )
        response = self.client.get(
            reverse("inventory:picker"),
            {"project": self.project.pk, "q": "cement"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["results"]
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], item.pk)

    def test_positive_balance_record_cannot_be_archived(self):
        item = self.add_item_stock("5").movement.stock_item
        response = self.client.post(
            reverse("inventory:status", kwargs={"reference": item.reference}),
            {"action": "archive"},
        )
        self.assertRedirects(
            response, reverse("inventory:detail", kwargs={"reference": item.reference})
        )
        item.refresh_from_db()
        self.assertEqual(item.status, StockItem.Status.ACTIVE)

    def test_zero_balance_record_can_be_archived_and_reactivated(self):
        item = self.create_item()
        status_url = reverse("inventory:status", kwargs={"reference": item.reference})
        self.client.post(status_url, {"action": "archive"})
        item.refresh_from_db()
        self.assertEqual(item.status, StockItem.Status.ARCHIVED)
        self.client.post(status_url, {"action": "reactivate"})
        item.refresh_from_db()
        self.assertEqual(item.status, StockItem.Status.ACTIVE)



class PrivateMovementAttachmentTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp_dir.name)
        self.override.enable()
        self.user = User.objects.create_user(username="keeper", password="safe-password")
        self.project = Project.objects.create(code="ARAMCO-01", name="Aramco Construction")
        self.unit = Unit.objects.get(normalized_name="bag")
        self.movement = add_stock(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            quantity=Decimal("5"),
            movement_date=timezone.localdate(),
            project=self.project,
            material_name="Portland Cement",
            supplier_name="Gulf Cement",
            supplier_phone="+966 57 368 6575",
            unit=self.unit,
            attachment=SimpleUploadedFile("invoice.pdf", b"test-pdf", "application/pdf"),
        ).movement

    def tearDown(self):
        self.override.disable()
        self.temp_dir.cleanup()

    def test_attachment_requires_login(self):
        url = reverse(
            "inventory:movement_attachment",
            kwargs={"reference": self.movement.reference},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Disposition"], 'attachment; filename="invoice.pdf"')
