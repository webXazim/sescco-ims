import json
from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.rental_manpower.services import create_supplier


class RentalMasterApiTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Acme", slug="acme-rental-api")
        self.user = User.objects.create_user(username="rental-api", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(self.user)
        self.supplier = create_supplier(
            actor_membership=self.membership,
            code="SUP-API",
            name="API Supplier",
        )

    def test_create_project_and_worker_endpoints_persist_masters(self):
        project_response = self.client.post(
            reverse("rental_manpower:projects-api"),
            data=json.dumps(
                {
                    "code": "",
                    "name": "API Project",
                    "start_date": date(2026, 1, 1).isoformat(),
                    "status": "Active",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(project_response.status_code, 201)
        self.assertTrue(project_response.json()["project"]["code"].startswith("PRJ-"))
        self.assertEqual(project_response.json()["project"]["id"], project_response.json()["project"]["reference"])

        worker_response = self.client.post(
            reverse("rental_manpower:workers-api"),
            data=json.dumps(
                {
                    "worker_number": "",
                    "full_name": "API Worker",
                    "supplier_id": str(self.supplier.pk),
                    "national_id": "API-NID",
                    "status": "Active",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(worker_response.status_code, 201)
        payload = worker_response.json()["worker"]
        self.assertEqual(payload["name"], "API Worker")
        self.assertEqual(payload["supplierId"], str(self.supplier.pk))
        self.assertIsNone(payload["projectId"])

    def test_project_detail_uses_shared_uuid_reference(self):
        from apps.rental_manpower.services import create_project

        project = create_project(
            actor_membership=self.membership,
            code="SHARED-API",
            name="Shared API Project",
            start_date=date(2026, 1, 1),
        )
        response = self.client.patch(
            reverse("rental_manpower:project-detail-api", kwargs={"project_id": project.reference}),
            data=json.dumps({"manager": "Rental Manager"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()["project"]
        self.assertEqual(payload["id"], str(project.reference))
        self.assertEqual(payload["manager"], "Rental Manager")

    def test_supplier_list_supports_search_sort_and_pagination(self):
        create_supplier(actor_membership=self.membership, code="SUP-Z", name="Zulu Supplier")
        create_supplier(actor_membership=self.membership, code="SUP-A", name="Alpha Supplier")
        response = self.client.get(
            reverse("rental_manpower:suppliers-api"),
            {"q": "Supplier", "sort": "name", "direction": "desc", "page": 1, "page_size": 2},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual([row["name"] for row in payload["results"]], ["Zulu Supplier", "API Supplier"])
        self.assertEqual(payload["meta"]["count"], 3)
        self.assertEqual(payload["meta"]["pageSize"], 2)
        self.assertEqual(payload["meta"]["totalPages"], 2)

    def test_supplier_list_rejects_unknown_sort(self):
        response = self.client.get(reverse("rental_manpower:suppliers-api"), {"sort": "unsafe"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_list_suppliers_is_company_scoped(self):
        other_company = Company.objects.create(name="Other", slug="other-rental-api")
        other_user = User.objects.create_user(username="other-rental-api")
        other_membership = CompanyMembership.objects.create(
            company=other_company,
            user=other_user,
            role=AccessRole.OWNER,
        )
        create_supplier(actor_membership=other_membership, code="OTHER", name="Other Supplier")
        response = self.client.get(reverse("rental_manpower:suppliers-api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["code"] for row in response.json()["results"]}, {"SUP-API"})

    def test_bulk_import_endpoint_validates_then_creates(self):
        rows = [
            {
                "worker_number": "",
                "full_name": "Imported Worker",
                "national_id": "IMPORT-NID",
                "supplier_id": str(self.supplier.pk),
                "status": "Active",
            }
        ]
        dry = self.client.post(
            reverse("rental_manpower:workers-import-api"),
            data=json.dumps({"rows": rows, "dry_run": True}),
            content_type="application/json",
        )
        self.assertEqual(dry.status_code, 200)
        self.assertEqual(dry.json()["validated"], 1)
        self.assertEqual(dry.json()["created"], 0)

        response = self.client.post(
            reverse("rental_manpower:workers-import-api"),
            data=json.dumps({"rows": rows}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["created"], 1)
        self.assertEqual(response.json()["workers"][0]["name"], "Imported Worker")

    def test_unauthenticated_request_returns_json_401(self):
        self.client.logout()
        response = self.client.get(reverse("rental_manpower:suppliers-api"))
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["ok"])

    def test_internal_only_role_cannot_access_rental_api(self):
        internal_user = User.objects.create_user(username="internal-rental-api", password="test-password")
        CompanyMembership.objects.create(
            company=self.company,
            user=internal_user,
            role=AccessRole.INTERNAL_PAYROLL_OFFICER,
        )
        self.client.force_login(internal_user)
        response = self.client.get(reverse("rental_manpower:suppliers-api"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["ok"])


class RentalAssignmentApiTests(TestCase):
    def setUp(self):
        from apps.rental_manpower.services import create_project, create_worker
        self.company = Company.objects.create(name="Assignment API", slug="assignment-api")
        self.user = User.objects.create_user(username="assignment-api-user", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(self.user)
        self.supplier = create_supplier(actor_membership=self.membership, code="SUP-ASG", name="Assignment Supplier")
        self.project = create_project(
            actor_membership=self.membership,
            code="PRJ-ASG",
            name="Assignment Project",
            start_date=date(2026, 1, 1),
        )
        self.worker = create_worker(
            actor_membership=self.membership,
            supplier_id=self.supplier.pk,
            worker_number="RW-ASG",
            full_name="Assignment Worker",
        )

    def test_assignment_action_endpoint_updates_worker_and_history(self):
        response = self.client.post(
            reverse("rental_manpower:assignments-api"),
            data=json.dumps({
                "action": "assign",
                "worker_id": str(self.worker.pk),
                "project_id": str(self.project.reference),
                "trade": "Helper",
                "rate_type": "Hourly",
                "rate": "11.25",
                "effective_date": "2026-01-01",
                "reason": "Initial deployment",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertEqual(payload["worker"]["status"], "Assigned" if date.today() >= date(2026, 1, 1) else "Scheduled")
        self.assertEqual(len([row for row in payload["assignments"] if row["kind"] == "assignment"]), 1)


    def test_future_assignment_can_be_cancelled_without_effective_date(self):
        future_date = date.today() + timedelta(days=14)
        create_response = self.client.post(
            reverse("rental_manpower:assignments-api"),
            data=json.dumps({
                "action": "assign",
                "worker_id": str(self.worker.pk),
                "project_id": str(self.project.reference),
                "trade": "Helper",
                "rate_type": "Hourly",
                "rate": "11.25",
                "effective_date": future_date.isoformat(),
                "reason": "Scheduled mobilization",
            }),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        cancel_response = self.client.post(
            reverse("rental_manpower:assignments-api"),
            data=json.dumps({
                "action": "cancel",
                "worker_id": str(self.worker.pk),
                "reason": "Mobilization cancelled",
            }),
            content_type="application/json",
        )
        self.assertEqual(cancel_response.status_code, 200)
        payload = cancel_response.json()
        self.assertEqual(payload["worker"]["status"], "Available")
        cancelled = [row for row in payload["assignments"] if row["kind"] == "assignment"][0]
        self.assertEqual(cancelled["status"], "Cancelled")
        self.assertEqual(cancelled["cancelReason"], "Mobilization cancelled")

    def test_invalid_rate_is_controlled_400(self):
        response = self.client.post(
            reverse("rental_manpower:assignments-api"),
            data=json.dumps({
                "action": "assign",
                "worker_id": str(self.worker.pk),
                "project_id": str(self.project.reference),
                "trade": "Helper",
                "rate_type": "Hourly",
                "rate": "0",
                "effective_date": "2026-01-01",
            }),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
