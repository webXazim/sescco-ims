# Project Pulse Upgrade 5 — Django Test Compatibility Fix

This patch is to be applied **only on the exact Upgrade 5/5 source**, not on older installations.

## Why the 121-test run failed

- `test_category_form_requires_name_only` and `test_category_edit_preserves_legacy_description_order_weight` expected `302` after a form POST, but production `SECURE_SSL_REDIRECT=True` returned `301` before the view ran. In `test_work_import_foundation.py`, tests now explicitly disable HTTPS redirection and use plain static-file storage, consistent with the rest of this module's test cases. **Application production security is not changed.**
- `test_project_overview_orders_categories_and_preserves_work_counts` and `test_progress_is_not_financial_and_project_dashboard_scoped` still asserted the old `Execution progress` label. Upgrade 4 intentionally renamed the interface to `Work Progress`. Those assertions now check the actual `h2` Work Progress heading using Django's HTML-aware assertion.

## Application change scope

Only **three test files** are modified; all views, URL routes, models, migrations, data and security settings remain byte-for-byte unchanged compared with the prior full Upgrade 5 ZIP.

## Verify in the deployed application test environment

```bash
python manage.py test apps.project_pulse.tests.test_work_import_foundation apps.project_pulse.tests.test_progress apps.project_pulse.tests.test_execution_schedule
python manage.py test apps.project_pulse
```

If running in Docker, use `docker compose exec ims_web python manage.py test apps.project_pulse` inside the application deployment. This runs Django tests against its temporary test database; it does not apply migrations to your production database. **Do not disable `SECURE_SSL_REDIRECT` in production to solve the test failures.**

## Verification limits

Python syntax, assertions-to-template alignment, modified-file scope and ZIP CRC checks can be verified offline. The Django test runner is not available in this packaging environment; the user must run tests in the configured Django environment to confirm the suite status. If the suite still reports failures, provide the entire test log, including the first two failures above the screenshot.
