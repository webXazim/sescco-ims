from .base import *  # noqa: F403

DEBUG = True
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Development/test fallback only. Production requires an explicit stable Fernet key.
if not PAYROLL_FIELD_ENCRYPTION_KEY:  # noqa: F405
    import base64
    import hashlib

    PAYROLL_FIELD_ENCRYPTION_KEY = base64.urlsafe_b64encode(  # noqa: F405
        hashlib.sha256((SECRET_KEY + ":payroll-fields").encode()).digest()  # noqa: F405
    ).decode()
