# SESCCO IMS — Project Pulse U10 release hardening

**Version:** 1.0.127  
**Based on:** complete U09 v1.0.126 release  
**Status:** Code-level hardening completed; staging/runtime acceptance pending  
**Database:** No new tables, columns, permissions or migration in U10. Existing U01–U09 migrations remain required.

## Verified and corrected issues

1. **Overview-only project information exposure:** Project Pulse home previously gave individual project codes, names, clients and completion dates to members who had only `pulse.overview.view` and not `pulse.projects.view`. U10 keeps permitted aggregate counts but withholds the project listing and task summaries until the project-view grant is present. The Project directory and detail screens already required that permission.
2. **Misleading budget variance when a category has no budget:** A report previously described `(sum of approved budgets) − (cost of all categories)` as the "Balance against set budgets." That incorrectly charged unbudgeted costs against other categories' approved budgets. U10 reports a separate **Balance on approved budgets**, separately identifies **unbudgeted approved cost**, and still includes all approved expenses in project cost. Project detail and category budget screens now use the accurate label/value.
3. **Archived unbudgeted approved expenses:** If a category was archived with expenses but without a budget, budget coverage could be marked complete. U10 treats such costs as incomplete budget coverage and withholds planned profit rather than implying a complete project budget.
4. **Stale foundation test:** The original U01 test expected exactly 10 Project Pulse permission entries. After U02–U09 this fails for legitimate new permissions. U10 checks the original base permissions are still present and the full catalog matches current registered Pulse grants.

## Added release verification

- `apps/project_pulse/tests/test_release_hardening.py`: three Django regression tests for approved-versus-unbudgeted cost balance, archived unbudgeted cost/planned profit, and budget UI warnings; existing foundation test expanded for privacy.
- `scripts/project_pulse_u10_offline_checks.py`: dependency-light AST/route/template/permission-migration/privacy checks, plus real XLSX and PDF generation smoke tests using the pinned exporter libraries; usable even without Django.
- `scripts/verify-project-pulse-u10.sh`: one staging verification command to execute offline checks, Django checks, migration planning and all Pulse tests. Does **not** run production migrations automatically.
- `PROJECT_PULSE_U10_STAGING_ACCEPTANCE.md`: manual staging and security acceptance checklist, including rollback preparation, receipt-volume backup and cross-module regression testing.

## Local checks executed

- Python syntax/AST: **705 source files** passed.
- Project Pulse URL/view and template references: **46 named routes** checked.
- Current access catalog versus latest permission migration: **124 values**, including **27 Project Pulse grants**, aligned.
- XLSX/PDF actual serializer smoke: **116 rows**, with formula-like text stored as a literal Excel string and a valid multi-page-capable PDF generated.
- `bash -n` succeeded for relevant backup, restore and verification scripts.
- Release ZIP integrity and preservation checks documented in release verification results.

## Staging commands (configured Python/DB)

```bash
bash scripts/verify-project-pulse-u10.sh
python manage.py migrate
python manage.py collectstatic --noinput
```

Test and back up before applying migrations. Do not use the new ZIP to overwrite a running production app without verifying existing data, custom access profiles and receipt storage.

## Important limitation

Django and `psycopg` were not installed in this preparation environment and package installation was unavailable. Accordingly, **Django regression tests, migration consistency against PostgreSQL, HTTP permission tests, full browser flows and backup restoration have not been executed**. This must be completed in staging before claiming production-ready status. Full Arabic PDF shaping also remains unverified.

All U01–U09 module functionality and the separate Inventory/Payroll expense architecture are retained. U10 is a hardening release, not another functional subsystem.
