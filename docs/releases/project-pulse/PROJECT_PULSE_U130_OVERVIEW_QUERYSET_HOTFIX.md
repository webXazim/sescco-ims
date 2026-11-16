# Project Pulse v1.0.130 — Overview queryset hotfix

## Failure
The project detail view converted a WorkCategory queryset to a Python list and then tried to call `.order_by()` on the list. All requests to the affected project overview could fail with `AttributeError: 'list' object has no attribute 'order_by'`.

## Correction
Sort and annotate the queryset **before** materializing it with `list()`. Preserve the `pulse_can_view_categories` access gate, category counts, ordering, and financial scoping.

An older progress regression test expected the previous UI label `Physical work progress`; it now checks the rendered `Execution progress` label. A regression test checks correct project overview rendering, category order, and work counts. No data model or migration changes.

## Verification on Ubuntu (staging)
```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse --noinput
```

Run with the application's normal Docker/staging settings and collect static files first if the environment uses manifest storage. Deploy to production only after tests pass and the normal preflight succeeds.
