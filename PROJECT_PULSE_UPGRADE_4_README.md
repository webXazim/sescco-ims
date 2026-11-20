# Project Pulse — Upgrade 4/5 (Work Progress UI and workflow)

Base: `Project_Pulse_Upgrade_3_of_5_Full_Source.zip`. This release **includes Upgrades 1–3**; do not overlay an older source tree over it.

## Changed experience

- Project-specific navigation now exposes `Work Progress`, `Works`, and (where authorized on active projects) `Import Works`. Old named routes and `/execution-schedule/` and `/scheduled-works/` URLs remain usable for existing links.
- `Work Progress`: category-name-only listing, optional category search, whole-project percentage summary (only for viewers with Progress permission), work counts, category progress, actions and empty states.
- `Works`: search by serial number, unit or description; filter by work category/status; shows `SN`, `Work`, `Work Category`, `Unit`, `Quantity`, `Completion`, `Status`, and actions. Completion and links remain permission controlled.
- Category detail: similarly compact work table, section progress, direct Update % links and existing authorized finance cards.
- Work creation: main fields first (category, SN, work, unit, quantity). Optional planning fields are preserved in a collapsible section. The category form remains name-only.
- Progress editor: numeric 0–100 field and optional synced range slider, plus exception status and note. The existing server form and audited progress service remain authoritative; JavaScript is not needed to save a numeric percentage.
- Excel import upload: concise single-sheet instructions and inline example; blank `% Completion` means **0%**. Preview: grouped by Work Category, new/changed/unchanged counts, work metadata, and per-row choices. Existing percentage defaults to **keep existing**, even when incoming Excel percentage is blank and parsed as 0%.
- Project overview, sidebar, and reporting labels use the new Work Progress / Work Category / Works terms.

## Safety and compatibility

- **No migrations added in Upgrade 4.** Existing migrations from Upgrades 1–3 still need to be applied in order.
- No inventory, payroll, expense, budget, contract, or approval business operations were changed.
- No work or category records are deleted or replaced as part of the UI upgrade.
- Old route names `execution_schedule`, `scheduled_works`, `categories`, and `tasks` remain available. New aliases are `work_progress` and `works`.
- Route/view permissions, import decisions, CSRF validation, progress audit trail and project scope restrictions remain enforced server-side.
- The source includes new `test_work_progress_ui_u4.py` tests and updated old UI label assertions.

## Staging validation (must run with Django configured)

1. Back up the database and deploy the **full ZIP** or patch over Upgrade 3.
2. `python manage.py check`
3. `python manage.py migrate --noinput` (Upgrade 4 introduces no new migration; catch up on U1–U3 if needed).
4. `python manage.py test apps.project_pulse`
5. Verify Work Progress, Works, add/edit category, work, percentage history, the grouped import preview, a reimport and role-limited accounts in the browser.
6. Smoke-test Inventory and financial workflow links prior to production release.

## Verification scope

Static source and template checks can run offline. Full Django integration tests, migrations against a database, and browser visual QA require a configured Django environment and were **not executed in the packaging environment**.

Next planned step: Upgrade 5/5 — integrated regression, migrations, permission verification, end-to-end import and release-readiness review.
