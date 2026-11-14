# SESCCO IMS v1.0.129 — Static manifest/test-order repair

## Problem
The new wheel guard is packaged at `static/platform/js/prevent-wheel-value-changes.js`,
but `scripts/release-tasks.sh` ran Project Pulse template-rendering tests before
`collectstatic`, so the persistent `ManifestStaticFilesStorage` manifest might not
contain the new path yet. The new `test_execution_schedule.py` also omitted the
standard test-only staticfiles storage override used by older Pulse tests.

## Changes
1. Collect static assets **before** Django regression tests; preserve old release
   files by using `collectstatic --noinput` without `--clear`.
2. Verify the strict production hashed manifest includes the shared wheel guard,
   and that its collected hashed file physically exists; fail deployment if missing.
3. Give the isolated execution-schedule test class the same non-manifest storage
   override already used by other Project Pulse unit tests. Production still uses
   strict ManifestStaticFilesStorage and independently verifies it.
4. Ensure the live Nginx gateway smoke test fetches the new wheel-guard JavaScript.
5. Add source/ordering contract checks to prevent regressions.

No database schema, permissions, finances, or stock history are modified.
The release remains **1.0.129** because this is a deployment hotfix.

## Validation on Ubuntu

```bash
sudo bash scripts/verify-production-freeze.sh
sudo bash scripts/deploy-production.sh
```

The deployment release tasks will now collect and validate the production
manifest **before** running Project Pulse and Sourcing tests. If testing a
previously built image without the patch, an interim workaround is to run
`collectstatic --noinput` in that image before its test suite, but using the
corrected release is recommended.
