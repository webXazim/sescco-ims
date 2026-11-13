# Project Pulse U06 — Expense Approval, Private Evidence & Payment Tracking

**Release:** SESCCO IMS v1.0.123  
**Baseline:** Full U05 source v1.0.122  
**Status:** Code implemented, static checks passed. Django database/HTTP tests have not run in this build environment.

## What is included

- **Approval states:** draft → submitted/pending → approved or rejected. Rejected expenses may be edited, returning them to draft before resubmission. Draft, pending and rejected expenses do **not** count as approved project cost.
- **Existing U05 entries:** migrated to **draft**. No historical entry becomes approved silently. These need review/approval before their costs appear in approved totals.
- **Approval authority:** `pulse.expenses.approve`; explicitly granted only to built-in company Owner profiles by migration. Other profiles must be configured individually. Non-Owner recorders cannot approve or reject their own expense even if their profile has approval authority.
- **Payments:** partial/full payments against approved entries, remaining balance, separate payment dates/methods/references. Payment service serializes updates and prevents overpayment. Payments cannot be edited/deleted; authorized corrections void a payment with a reason and allow a replacement payment. Payments may settle completed/on-hold projects but not archived/deleted projects.
- **Private attachments:** receipts/evidence in PDF, PNG, JPEG or WebP (10 MB max), stored outside MEDIA_ROOT and STATIC_ROOT. Download checks project scope and confidential expense permission, forces attachment response and disables response caching. Files remain historical; they are not publicly linked.
- **Financial summaries:** approved, pending, all-recorded, and paid SAR totals shown separately. Work-category and project approved totals exclude drafts/rejected/voided expenses and include archived tasks' historically approved costs. Payroll and Inventory remain independent.
- **Audit:** expense approvals use the restricted `PulseExpenseChange` snapshots; payment and attachment records are retained. General audit events omit confidential amounts, suppliers and receipt filenames.
- **Interfaces:** per-project pending approvals, per-expense detail, review, attachments, payments and reversals, plus status filters on the project expense ledger.

## New permissions

- `pulse.expenses.approve`: review pending expenses (requires `pulse.expenses.view`).
- `pulse.expense_payments.manage`: create/void payments (requires `pulse.expenses.view`).
- `pulse.expense_attachments.manage`: upload private evidence (requires `pulse.expenses.manage` and its view dependencies).

All write routes enforce the profile and company/project scope in backend services and views. The system Owner profile is granted these three codes by `apps/accounts/migrations/0022_project_pulse_u06_approval_authority.py`.

## New migrations

- `apps/accounts/migrations/0022_project_pulse_u06_approval_authority.py`
- `apps/project_pulse/migrations/0005_expense_approvals_payments_evidence.py`

Expense approval status defaults to **draft**, including records migrated from U05. No automatic approval or payment migration occurs.

## Deployment and important receipt storage requirement

**Back up the production database and media before upgrading.** Receipts introduced by U06 have a new storage directory. U06 updates backup, backup verification, and restore scripts to include `pulse-private.tar.gz` (and its checksum). Older pre-U06 backups are still readable; when restored they clear the private receipt volume because those backups contain no receipt evidence.

- Docker: U06 adds persistent volume `ims_pulse_private_data` mounted to `/app/private_uploads`, also available to the maintenance/tools service at `/data/pulse_private` for backup and restoration. The new receipt archive is included in backup verification and restore. Do not publish this volume through nginx or serve it as `/media/`.
- Non-Docker deployment: set `PULSE_PRIVATE_STORAGE_ROOT` to a **persistent, writable, private directory** outside your web server's static/media public URLs, and include this directory in your backups.
- Update your `APP_VERSION` environment setting to `1.0.123` if you display release versions via this variable.

In a configured/staging Django environment, after deploying the complete source:

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

For Docker, run these commands inside the web service, for example `docker compose exec ims_web python manage.py migrate`. Restart/redeploy only after successful migration and checks.

## Essential acceptance tests (before production)

1. Create draft expense, submit, reject with required reason, edit and resubmit, then approve as authorized reviewer. Only approved amount increases approved cost.
2. A custom profile without `pulse.expenses.view` receives 403 on expense detail, review queue, attachment download and payment routes.
3. A user with view+manage+approve cannot approve a payment they recorded themselves unless their role is the real company Owner.
4. Pending/approved expense fields cannot be changed silently; edits are limited to draft/rejected.
5. Record partial payments, prevent sum over approved amount, reverse payment with reason, preserve history, and repay difference.
6. Verify unauthorized project IDs cannot expose another project's expense, payments or receipts; verify company isolation.
7. Upload a valid receipt; reject HTML disguised as PDF and oversized upload. Confirm the downloaded file is private, authenticated, and not available at any public media URL.
8. Confirm an old U05 expense is draft after migration (never pre-approved) and can be submitted and approved.
9. Confirm payments can settle a completed or on-hold project but cannot change archived/deleted projects.
10. Verify Inventory, Payroll, Sourcing, Administration, U01–U05 task/progress features still work.

## Validation limitations

- Successfully parsed Python source and checked permission/migration values, URL-to-view/template linkage, and full ZIP integrity.
- Django itself is not installed in the available build environment. Database migrations, Django system checks, view tests, template compilation under Django, and integration regression tests **remain unexecuted**. Staging deployment and human review are mandatory before production use.

**Not included yet:** category budgets (U07), project contract and profitability calculations (U08), report export (U09), end-to-end runtime hardening (U10).
