## 5K/2K browser benchmark certification & production freeze (1.0.70)

- Confirm `VERSION` and Payroll static cache-busters are `1.0.70`.
- Run `python3 scripts/verify-payroll-browser-scale.py` and the complete `./scripts/verify-production-freeze.sh` gate.
- On the benchmark database, run `python manage.py payroll_browser_scale_report --require-benchmark-volume --fail-on-limits` and retain the output as `payroll-browser-scale-report.txt`.
- From a release/test workstation with Playwright + Chromium, run `python scripts/certify-payroll-browser-scale.py --base-url https://ims.sescco.com --username <benchmark-user> --password-env IMS_BROWSER_BENCHMARK_PASSWORD` and retain `payroll-browser-certification.json`.
- Verify Internal Attendance/OT, Rental Project Timesheets/OT, Assignment Activity/Deployment/Pool and Ctrl/Cmd+K global search remain bounded while rapidly typing, paging and switching routes.
- Do not certify the browser benchmark if any page remains in a loading state, if stale searches overwrite the final query, or if bounded tables exceed their 100-row server-page contract (Assignment Activity may expand 100 assignment segments into at most 200 lifecycle events).
- 1.0.70 adds no new schema migration or Payroll formula change; it carries the 1.0.69 PostgreSQL search indexes forward unchanged.

## PostgreSQL search & query hardening (1.0.69)

- Confirm `VERSION` and Payroll static cache-busters are `1.0.69`.
- Run `python3 scripts/verify-payroll-query-hardening.py`.
- Run `python manage.py migrate --plan` and confirm the new `pg_trgm`/concurrent index migrations are planned before deployment.
- After migration on benchmark data, run `python manage.py payroll_search_query_report --query RDEMO --explain` and inspect employee/worker/assignment plans and timings.
- Rapidly search Internal Employees, Internal Attendance, Rental Workforce and Assignment Activity while paging; no request should require a join/DISTINCT fan-out over complete assignment history.
- Run the complete packaged production-freeze gate before deployment.

## Thin Payroll bootstrap & server-backed global search (1.0.68)

- Confirm `VERSION` and Payroll static cache-busters are `1.0.68`.
- Run `python3 scripts/verify-payroll-bootstrap-search.py`.
- With benchmark seed, confirm initial Payroll navigation does not serialize/load the complete 2,000 Internal + 5,000 Rental worker masters.
- Verify Ctrl/Cmd+K searches employees/workers/projects/suppliers through bounded backend requests and cancels obsolete searches while typing quickly.
- Verify direct links to an employee or Rental worker outside the first 50 bootstrap rows hydrate the requested profile from the backend.
- Verify Salary Setup, Payroll Runs and WPS/Bank/Payments load their server contexts on demand and Adjustment selectors lazily hydrate complete masters only when required.
- Run the complete packaged production-freeze gate before deployment.

## Attendance & Timesheet scale cutover (1.0.67)

- Confirm `VERSION` is `1.0.67` and Payroll static cache-busters are `1.0.67`.
- Run `python3 scripts/verify-payroll-timesheet-scale.py`.
- With benchmark seed, verify Internal Attendance/OT remain responsive at 2,000 employees and Rental Project Timesheets remain responsive at 5,000 workers.
- Verify search, branch/department/supplier filters and 25/50/100 page changes cancel obsolete requests and never render a full workforce month.
- Verify single-cell and OT edits return delta payloads and do not reload the complete monthly dataset.
- Run the complete packaged production-freeze gate before deployment.

## Rental Assignment Lifecycle server pagination (1.0.66)

- Confirm `VERSION` is `1.0.66` and Payroll static cache-busters are `1.0.66`.
- Run `python3 scripts/verify-payroll-assignment-runtime.py`.
- On benchmark data, verify Activity, Current Deployment and Supplier Pool search/page changes stay responsive and only request bounded backend pages.
- Confirm assignment mutations refresh summary + active tab without a full browser history scan.

# Release checklist

- [ ] `.env.production` contains no placeholders and is mode 600.
- [ ] Required secrets were generated independently with `scripts/create-production-env.sh` (or an equivalent cryptographically secure process).
- [ ] `./scripts/preflight.sh` passes.
- [ ] `PAYROLL_FIELD_ENCRYPTION_KEY` is stored in an independent protected disaster-recovery secret store.
- [ ] `DJANGO_TRUSTED_PROXY_IPS` includes the confirmed `ims_edge` subnet `172.20.0.0/16`.
- [ ] `./scripts/verify-production-infrastructure.sh` passes.
- [ ] `./scripts/verify-production-freeze.sh` passes.
- [ ] Production cutover uses the canonical `./scripts/deploy-production.sh` entrypoint, which verifies the packaged production freeze itself.
- [ ] A current production backup has passed `./scripts/rehearse-production-freeze.sh`.
- [ ] Rehearsal evidence contains successful row-count preservation, legacy field-data fingerprint preservation, and SHA-256 checksums.
- [ ] `/app/health/ready/` reports both `database=ready` and `migrations=ready`.
- [ ] Backup manifest contains `payroll_field_key_fingerprint_sha256` and a restore with the wrong key is rejected.
- [ ] Inventory, shared-shell, and Payroll static smoke-test URLs return 200 after deploy.
- [ ] Python compilation and static validation pass.
- [ ] `python manage.py test` passes in Docker or CI.
- [ ] `python manage.py check --deploy` passes.
- [ ] `makemigrations --check --dry-run` reports no drift.
- [ ] A pre-release database and media backup exists.
- [ ] `ims.sescco.com` DNS resolves to the correct VPS.
- [ ] TLS certificate is valid and HTTPS redirect works.
- [ ] Login, add stock, use stock, filtering and exact export are smoke-tested.
- [ ] Storekeeper cannot access `/admin/`.
- [ ] Private attachment URLs require authentication.
- [ ] Backup checksum verification passes.
- [ ] A restore test has been completed in an isolated environment.

## Payroll directory runtime hotfix (1.0.65)

- Confirm `VERSION` is `1.0.65` and Payroll static cache-busters are `1.0.65`.
- Run `python3 scripts/verify-payroll-directory-runtime.py`.
- Verify rapid search typing cancels obsolete requests and a completed directory request clears loading before rendering.
- Verify Branches, Departments, Internal Employees, Projects, Suppliers and Rental Workforce retain bounded server pagination.
- Run the complete packaged production-freeze gate before deployment.

## Final production freeze / release candidate (1.0.64)

- Run `python3 scripts/verify-release-candidate.py` and `./scripts/verify-production-freeze.sh` against the exact packaged source tree.
- Confirm `VERSION` is `1.0.64` and the Payroll static cache-busters are `1.0.64`.
- Confirm the predecessor artifact SHA-256 is `8291351ac88c883796d899f31fbffbb32416b79f53e1ad8be1d3485fd0049d9e` for `sescco-ims-1.0.63-full-payroll-production-e2e-certification.zip`.
- Do not add features, schema changes or Payroll formula changes after the final freeze is generated. Any such change requires a new release/version.
- Before production cutover, run the isolated rehearsal so deployment checks, zero migration drift, curated Payroll E2E tests and the full Django suite produce runtime evidence.

## Payroll production E2E certification (1.0.63)

- Run `python3 scripts/verify-payroll-production-e2e.py` before image build.
- In an environment with Django/PostgreSQL available, run `bash scripts/certify-payroll-production-e2e.sh` against an isolated test database.
- Production rehearsal must retain `payroll-e2e-certification.txt` alongside the other migration/reconciliation evidence.
- Do not certify the final release from static checks alone; the dedicated Django suite must pass in the release/rehearsal environment.
