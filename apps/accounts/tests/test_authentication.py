from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.tests.tenant import grant_company_access

User = get_user_model()


class AuthenticationFlowTests(TestCase):
    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("core:dashboard"))
        self.assertRedirects(
            response,
            f"{reverse('accounts:login')}?next={reverse('core:dashboard')}",
        )

    def test_storekeeper_is_redirected_to_workspace(self):
        user = User.objects.create_user(username="storekeeper", password="safe-password")
        grant_company_access(user)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_company_owner_is_redirected_to_workspace(self):
        user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="safe-password",
        )
        grant_company_access(user)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:home"))
        self.assertRedirects(response, reverse("core:dashboard"))

    def test_logout_requires_post(self):
        user = User.objects.create_user(username="storekeeper", password="safe-password")
        grant_company_access(user)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

    def test_storekeeper_cannot_log_into_django_admin(self):
        user = User.objects.create_user(username="keeper2", password="safe-password")
        grant_company_access(user)
        self.client.force_login(user)
        response = self.client.get(reverse("admin:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response.url)
