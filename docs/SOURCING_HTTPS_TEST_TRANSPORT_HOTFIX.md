# Sourcing HTTPS Test Transport Hotfix

Release 1.0.116 fixes a production-image test transport mismatch. Production enables `SECURE_SSL_REDIRECT`, while Django's test client issues HTTP requests by default. SecurityMiddleware therefore returned HTTP 301 before Sourcing view authorization ran.

The hotfix does not change production HTTPS behavior. It applies `@override_settings(SECURE_SSL_REDIRECT=False)` only to Sourcing test classes whose purpose is to validate application permissions, tenant isolation, CRUD behavior, lifecycle behavior, finders, verification, and data exchange.

The production setting remains enabled by default. The expected application-level outcomes therefore become observable again in tests, including Vendor-viewer `200`, unauthorized Storekeeper `403`, foreign-company `404`, and direct mutation denial.

No migration, database change, permission-catalog change, Payroll formula change, Inventory quantity change, Sourcing business-rule change, or production security-policy change is introduced.
