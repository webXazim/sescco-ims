# Project Pulse U10 — Receipt Test Cleanup Correction

Version: 1.0.127 (unchanged)

## Symptom

`test_private_evidence_validation_and_project_isolation` raises
`AttributeError: 'NoneType' object has no attribute 'close'` after a successful
receipt download. Some middleware can wrap `streaming_content`, leaving
`response.file_to_stream` as `None`.

## Change

Use a public `response.streaming` assertion instead of manually closing the
private `response.file_to_stream` attribute. Do not call `response.close()`
inside this `django.test.TestCase`, because `request_finished` can close the
PostgreSQL connection that owns the test transaction. Normal test cleanup
releases the response and its resources.

The private receipt download view is **unchanged**. The test still verifies a
successful download, no-store cache header and cross-project 404 isolation.
Warnings for expected 403/404 access-control tests are not deployment errors.

## Validation

Passed: source parsing, entire archive Python syntax verification,
archive integrity and exact archive diff (only this test and release note).

Not run here: Django/PostgreSQL runtime test suite. Run in staging:

```
python manage.py test apps.project_pulse.tests.test_workflow.ExpenseWorkflowTests.test_private_evidence_validation_and_project_isolation --verbosity 2
python manage.py test apps.project_pulse --verbosity 2
```

No database migrations, production settings changes or version bump.
