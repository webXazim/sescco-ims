from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.core.middleware import RequestIdMiddleware


class HealthEndpointTests(TestCase):
    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_liveness_does_not_require_authentication(self):
        response = self.client.get(reverse("core:health_live"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_readiness_checks_database(self):
        response = self.client.get(reverse("core:health_ready"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["database"], "ready")
        self.assertEqual(response.json()["migrations"], "ready")

    @override_settings(SECURE_SSL_REDIRECT=False)
    @patch("apps.core.views.MigrationExecutor")
    def test_readiness_rejects_pending_migrations(self, executor_class):
        executor_class.return_value.loader.graph.leaf_nodes.return_value = [("core", "9999_future")]
        executor_class.return_value.migration_plan.return_value = [object()]

        response = self.client.get(reverse("core:health_ready"))

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["database"], "ready")
        self.assertEqual(response.json()["migrations"], "pending")
        self.assertEqual(response.json()["pending_migration_count"], 1)


class RequestIdMiddlewareTests(TestCase):
    def test_generates_request_id(self):
        request = RequestFactory().get("/")
        response = RequestIdMiddleware(lambda request: HttpResponse())(request)
        self.assertRegex(response["X-Request-ID"], r"^[a-f0-9]{32}$")

    def test_preserves_valid_upstream_request_id(self):
        request = RequestFactory().get("/", HTTP_X_REQUEST_ID="ims-request-1234")
        response = RequestIdMiddleware(lambda request: HttpResponse())(request)
        self.assertEqual(response["X-Request-ID"], "ims-request-1234")
