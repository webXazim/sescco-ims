from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership, User
from apps.accounts.roles import AccessRole
from apps.core.models import Company
from apps.rental_manpower.services import create_project


class AssignmentProjectLookupTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name="Lookup Co", slug="assignment-project-lookup")
        self.user = User.objects.create_user(username="assignment-project-lookup", password="test-password")
        self.membership = CompanyMembership.objects.create(
            company=self.company,
            user=self.user,
            role=AccessRole.RENTAL_MANPOWER_OFFICER,
        )
        self.client.force_login(self.user)
        self.projects = [
            create_project(
                actor_membership=self.membership,
                code=f"SCALE-P-{index:03d}",
                name=f"Scale Target Project {index:03d}",
                start_date=date(2026, 1, 1),
                status="Active",
            )
            for index in range(13)
        ]
        self.future_project = create_project(
            actor_membership=self.membership,
            code="SCALE-P-FUTURE",
            name="Scale Target Future Project",
            start_date=date(2026, 10, 1),
            status="Active",
        )

    def test_lookup_requires_search_and_uses_bounded_count_free_pages(self):
        url = reverse("rental_manpower:assignment-project-lookup-api")
        short = self.client.get(url, {"q": "S", "effective_date": "2026-09-14", "page_size": 10})
        self.assertEqual(short.status_code, 200)
        self.assertTrue(short.json()["requiresQuery"])
        self.assertEqual(short.json()["results"], [])

        first = self.client.get(
            url,
            {
                "q": "Scale Target",
                "effective_date": "2026-09-14",
                "exclude_project_id": str(self.projects[0].reference),
                "page": 1,
                "page_size": 10,
            },
        )
        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertEqual(len(payload["results"]), 10)
        self.assertTrue(payload["meta"]["hasNext"])
        self.assertFalse(payload["meta"]["hasPrevious"])
        self.assertNotIn("count", payload["meta"])
        self.assertNotIn("totalPages", payload["meta"])
        ids = {row["id"] for row in payload["results"]}
        self.assertNotIn(str(self.projects[0].reference), ids)
        self.assertNotIn(str(self.future_project.reference), ids)

        second = self.client.get(
            url,
            {
                "q": "Scale Target",
                "effective_date": "2026-09-14",
                "exclude_project_id": str(self.projects[0].reference),
                "page": 2,
                "page_size": 10,
            },
        )
        self.assertEqual(second.status_code, 200)
        payload2 = second.json()
        self.assertEqual(len(payload2["results"]), 2)
        self.assertFalse(payload2["meta"]["hasNext"])
        self.assertTrue(payload2["meta"]["hasPrevious"])

    def test_lookup_caps_requested_page_size_at_twenty_five(self):
        url = reverse("rental_manpower:assignment-project-lookup-api")
        response = self.client.get(
            url,
            {"q": "Scale Target", "effective_date": "2026-09-14", "page_size": 500},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["pageSize"], 25)
        self.assertEqual(response.json()["limit"], 25)
