# Project Pulse — U10 test-failure repair (v1.0.127)

Base: SESCCO_IMS_v1.0.127_EnvVersion_RootCleanup_Full.zip. No database schema or migration changes. The production APP_VERSION remains 1.0.127.

## Source fixes
- Re-read/lock selected expense categories from PostgreSQL when creating or editing expenses; archived categories cannot be reused through an outdated in-memory category object. Preserve existing archived-category history.
- Cross-company expense-service regression now expects HTTP 404, matching the intentional non-disclosure behavior (rather than PermissionDenied).
- Expense evidence download regression explicitly closes only the FileResponse's file descriptor. Calling response.close() inside a Django TestCase can emit request_finished and close the PostgreSQL connection that the test's outer transaction depends on.
- U02/U03 regression tests now recognize that later Project Pulse upgrades intentionally added more permission types; task-only profiles are asserted to lack financial/budget/inventory grants instead of asserting those permissions do not exist anywhere.
- The task-creation HTTP regression now submits complete fields including weight/date defaults and prints actual form validation errors on failure; no task business-logic change.

## Verification
PASS: Python compileall (updated project_pulse package); U10 offline checks (AST, all 46 Pulse routes, permission catalog/constraint migration, finance/security guards, real Excel/PDF smoke tests); production source freeze verifier; both generated ZIP integrity checks.
NOT VERIFIED here: Django/PostgreSQL tests, HTTP integration and production deployment. They must run on the server. Previous log reported 85 tests, 4 failures and 3 errors.

## Apply
1. Back up application/database/private uploads. The hotfix contains only five files, under the sescco-ims/ directory.
2. Unzip to a temporary folder and copy those files into /opt/sites/ims, or extract the full updated application to staging (do NOT overwrite .env.production or live volumes).
3. Run: bash scripts/verify-production-freeze.sh
4. Review and commit source changes according to local release process.
5. Run release in staging; see scripts/verify-project-pulse-u10.sh for Django test commands. Production deploy runs regression checks as part of release-tasks.sh.
6. If errors persist, capture the COMPLETE test output from the start, especially the first error, rather than only its tail.
