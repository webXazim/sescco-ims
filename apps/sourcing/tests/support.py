"""Shared production-image test settings for the Sourcing HTTP test surface.

The production image intentionally uses ManifestStaticFilesStorage and HTTPS
redirects. Focused Django Client tests execute before deployment collectstatic,
so they must not depend on the shared production static manifest and must reach
the application view instead of being redirected by SecurityMiddleware.
"""

SOURCING_HTTP_TEST_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
