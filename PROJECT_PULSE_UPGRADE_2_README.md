# Project Pulse — Upgrade 2 of 5: Actual Percentage Progress

This ZIP is based on the Upgrade 1 full-source archive. **Deploy the complete full-source ZIP or apply the changed-files patch to Upgrade 1, not to an older code version.**

## What's changed

- Each eligible work contributes its **actual progress_percent (0–100)**, not only its Completed status.
- Each nonempty active work category averages its eligible work percentages. Each such category contributes equally to the project average, **without diluting progress with empty categories**. Display is rounded half-up to 1 decimal; calculations retain unrounded precision until the final project calculation.
- Archived categories, archived works and cancelled works are excluded. Counts of completed and overdue works remain separate.
- Work details (title, unit, quantity, etc.) can be edited without resetting progress. The normal work form no longer accepts status/progress changes; use **Update progress** to change percentage/status. Legacy service callers submitting a changed status must have progress-update permission, and cannot silently reset a completed work.
- Progress form: required whole number 0–100; status usually automatic (0 Not started; 1–99 In progress; 100 Completed); Blocked, On hold and Cancelled are explicit exceptions that preserve partial progress below 100%. Invalid combinations are rejected.
- Each confirmed progress update is atomic and preserves the existing append-only history and audit event. Old quick-completion POST route is retained for backward compatibility; ordinary user-facing lists now link to the percentage editor instead.
- Project/category/task screens and progress reports now display actual percentages.

## Deferred to later upgrades

- Upgrade 3: single-sheet Excel importer, including **blank completion cell = 0%** and safe reimports.
- Upgrade 4: full interface renaming and restructuring (Work Progress, Work Categories, Works, Import Works).
- Upgrade 5: integration and production-level verification, including finance/inventory/payroll regressions.

## Deployment steps

1. Back up application code and database before applying.
2. Apply this full-source ZIP, or only the changed-files patch over **Upgrade 1**.
3. If Upgrade 1 migration has not already been applied, run `python manage.py migrate` using your application's configured environment. Upgrade 2 adds **no database migration**.
4. Run `python manage.py check` and `python manage.py test apps.project_pulse` in staging.
5. Manually verify authorized users can update 0%, 30%, 65%, 100% and Blocked at 65%; verify change history and project/category totals. Check unauthorized and archived/hold states.
6. Verify progress and financial reports still respect permission scope and record consistency before production deployment.

## Notes

- The shipped Python source passed syntax compilation; Django integration tests were not runnable in this build environment because Django was not installed. Treat staging database, migration and integration validation as mandatory.
- No existing progress values or history are intentionally rewritten during installation.
