from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CompanyMembership
from apps.accounts.roles import AccessRole
from apps.core.models import Company


User = get_user_model()


class MergedPayrollFrontendTests(TestCase):
    def make_user(self, username: str, role: str):
        company = Company.objects.create(
            name=f"{username.title()} Company",
            legal_name=f"{username.title()} Company LLC",
            slug=f"{username}-company",
        )
        user = User.objects.create_user(username=username, password="strong-test-password")
        membership = CompanyMembership.objects.create(company=company, user=user, role=role)
        self.client.force_login(user)
        return user, company, membership

    def test_owner_can_open_namespaced_payroll_frontend(self):
        self.make_user("owner-ui", AccessRole.OWNER)
        response = self.client.get(reverse("core:payroll"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="payroll-access-context"')
        self.assertContains(response, "/static/payroll/css/v2/index.css")
        self.assertContains(response, "/static/payroll/js/app.js")
        self.assertNotContains(response, 'src="/static/js/app.js"')

    def test_internal_officer_can_open_payroll_frontend(self):
        self.make_user("internal-ui", AccessRole.INTERNAL_PAYROLL_OFFICER)
        response = self.client.get(reverse("core:payroll"))
        self.assertEqual(response.status_code, 200)

    def test_rental_officer_can_open_payroll_frontend(self):
        self.make_user("rental-ui", AccessRole.RENTAL_MANPOWER_OFFICER)
        response = self.client.get(reverse("core:payroll"))
        self.assertEqual(response.status_code, 200)

    def test_inventory_only_storekeeper_cannot_open_payroll_frontend(self):
        self.make_user("store-ui", AccessRole.STOREKEEPER)
        response = self.client.get(reverse("core:payroll"))
        self.assertEqual(response.status_code, 403)

    def test_payroll_only_home_redirects_to_payroll_frontend(self):
        self.make_user("finance-ui", AccessRole.FINANCE_MANAGER)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("core:payroll"), fetch_redirect_response=False)

    def test_owner_inventory_sidebar_exposes_payroll_entrypoint(self):
        self.make_user("owner-nav", AccessRole.OWNER)
        response = self.client.get(reverse("core:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("core:payroll"))
        self.assertContains(response, "Payroll Management")
