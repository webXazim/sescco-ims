# Project Pulse — Upgrade 3 of 5: Single-Sheet Works Import

This package is built on the **Upgrade 2 full-source ZIP**, including Upgrade 1's category and task fields and Upgrade 2's percentage-progress fixes. The full-source ZIP replaces the code tree; the changed-files ZIP must be applied **only over Upgrade 2**, not over the original IMS release.

## Import layout

One `.xlsx` worksheet (one selected project per upload):

| A | B | C | D | E |
|---|---|---|---|---|
| `Power Transformer` | | | | |
| `SN` | `Description` | `Unit` | `Quantity` | `% Completion` |
| `1` | `Transformer installation` | `EA` | `3` | *(blank = 0%)* |
| `2` | `AVC panels` | `EA` | `4` | `35` |
| `Cable Installation` | | | | |
| `SN` | `Description` | `Unit` | `Quantity` | `% Completion` |
| `1` | `Cable laying` | `LM` | `540` | `60%` |

A category heading has **only column A populated**. Repeat the header after each category. Repeated headings may refer to an existing category. Additional populated columns are errors. The importer rejects formulas, invalid percentages, duplicate SN within one category, and a second worksheet. Empty completion cells explicitly become **0%**; Excel cells formatted with `0%` correctly interpret numeric `0.25` as 25%. Quantity is optional and supports up to four decimal places. SN and Description are required.

## What's delivered

- `/projects/<code>/works/import/` file upload route, selected-project authorization, one-sheet format validation and errors with Excel row numbers.
- A review page with each new/changed/unchanged row, including **imported percentage and current percentage**.
- Import decisions: new rows **Create/Skip**; changed rows **Keep existing** (default), **Update details only**, or **Update details and percentage**. No existing work percentage is overwritten automatically even when the new Excel cell is empty (and therefore parsed as 0%).
- Project + company authorization for previews and commits, independent category/task manage permissions, and additional progress-update permission when importing a nonzero percentage or changing an existing percentage.
- Atomic application with project lock, stale preview verification, category+SN matching, append-only progress history, per-item audit events, and import-batch audit.
- Saved previews expire after one hour; the uploaded Excel bytes are **never stored**. Applied previews are immediately cleared. Expired previews for a project are cleared on that project's next import.
- On-page **Download blank template** link. File: `static/project_pulse/files/Works_Import_Template.xlsx`.
- Import actions on the existing Categories and Works pages; the complete UI renaming remains scheduled for Upgrade 4.
- Limits per file: 8 MB upload, 50 MB expanded XLSX, 2,500 works, 15,000 worksheet rows. One project is selected in the application, never supplied by Excel.
- Additive database migration `0009_work_import_preview.py` (two fields on the existing import-batch model).

## Important deployment procedure

1. **Back up code and database**. Test in a staging environment, not first on live data.
2. Deploy full-source ZIP or patch over **Upgrade 2**.
3. In the configured app environment run:
   - `python manage.py migrate`
   - `python manage.py check`
   - `python manage.py test apps.project_pulse`
4. Collect static assets as required by your existing deployment: `python manage.py collectstatic --noinput`.
5. In a staging ACTIVE project, import a small Excel file with one blank %, one `25`, one `25%`, and an Excel percentage-formatted cell. Verify status, totals, and audit history.
6. Reimport the same file, confirm nothing duplicates. Change an existing work's completion to 60% in the UI, then reimport a blank completion cell. Default confirmation must **preserve 60%**. Only choosing **Update details + percentage** may reset to 0%.
7. Check archiving, permissions, financial/expense associations, project scope, and large imports. Do not deploy before Django integration tests pass.

## Verification and limitations

- Python syntax checks completed.
- Direct parser smoke tests (outside Django) passed for category grouping, blank=0%, numeric percentages, Excel-formatted percentages, formula rejection, and the converted current BOQ workbook (9 categories / 151 works, 0 parse errors).
- A Django TestCase test module was added at `apps/project_pulse/tests/test_work_import_excel.py` but **could not be run in the build container, because Django is not installed here**. Staging tests remain required and the package is not asserted production-certified.
- Upgrade 4 will rename remaining pages/controls to Work Progress / Work Categories / Works, improve the UI, and integrate import more broadly.
- Upgrade 5 will complete full regression and deployment verification.
