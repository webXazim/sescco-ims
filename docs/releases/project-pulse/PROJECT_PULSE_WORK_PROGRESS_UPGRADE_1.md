# Project Pulse — Work Progress Upgrade 1/5: Database and Work Structure

This is **Upgrade 1 of 5**, based on SESCCO MS source release 1.0.128. It is an additive schema and category-form update, **not** the finished Excel importer.

## Implemented

- The category create/edit form exposes only **Work Category Name**. Stored legacy description, order and progress weight remain untouched when renamed.
- `PulseTask` supports optional **SN** (`serial_number`), **Unit** (`unit`), **Quantity** (`quantity`, four decimals, nonnegative), **import row number**, and **last import batch**.
- Task title can contain up to 1,000 characters for long BOQ work descriptions; the existing supplementary description field is preserved.
- Task form and audited task-saving service support SN, unit and quantity.
- A nonempty SN is unique *within the same category*, not across different categories. Existing tasks with empty SN continue to work.
- `PulseWorkImportBatch` stores project-scoped metadata for a confirmed upload in the later importer (filename, SHA-256 hash, uploader, status and counts). The workbook contents are **not** stored here.
- No Inventory, Payroll, expense, budget or authorization logic changed.

## Explicitly not yet implemented

- **Upgrade 2:** 0–100% progress editor, partial-progress calculation and status behavior.
- **Upgrade 3:** XLSX parsing, blank completion percentage defaulting to 0%, preview/validation, import and reimport matching.
- **Upgrade 4:** Work Progress page and all requested terminology/UI changes.
- **Upgrade 5:** Full test suite, PostgreSQL migration rehearsal and production acceptance.

The blank-percentage-to-zero requirement is preserved for the planned importer; Upgrade 1 does not yet parse Excel files.

## Migration and safe deployment

1. Back up PostgreSQL and media first. Do **not** overwrite a live production DB with test data.
2. Deploy to **staging** first, with project/app environment variables available.
3. Execute `python manage.py showmigrations project_pulse` and confirm migration 0007 is present.
4. Run `python manage.py migrate project_pulse` (adds `0008_work_import_foundation`).
5. Check `python manage.py check`, then `python manage.py makemigrations --check --dry-run` (should report no changes), and run the targeted test module:

   ```bash
   python manage.py test apps.project_pulse.tests.test_work_import_foundation
   ```

6. Verify that old category/task IDs, progress, status and expense relations are intact. Review PostgreSQL migration/lock behavior against the staging-sized database before production.

## Schema considerations

`PulseTask.serial_number` is intentionally optional to preserve older tasks. A nonempty number is unique per category; duplicate numbers must be corrected in a later import preview. `PulseWorkImportBatch` only enables provenance; it does not grant permission to import. All real uploads in Upgrade 3 must use existing category/task authority plus progress-update authority when applying nonzero progress. Import/reimport must be atomic and protect historical progress.
