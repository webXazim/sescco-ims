# SESCCO IMS — countable units and project inventory approvals

This upgrade adds database migrations and a project-manager approval workflow. It does not rewrite production stock history.

## Deploy

1. Back up the production database and uploaded media; deploy code and run `python manage.py migrate` using the project's existing Django environment.
2. Run `python manage.py check` and `python manage.py audit_quantity_units`.
3. Under **Administration → Access Profiles**, the built-in **Project Manager** access profile is available. In **Users**, assign this profile with **Selected Projects** scope. The profile grants *view and approve* privileges only; it does not grant stock receive/transfer/adjust permissions.
4. Under **Projects → Edit**, set **Project inventory approver** for each project. This field must point to a currently active user in the same company who has the `inventory.stock.approve` permission and access to that project. The old text-only `manager_name` field remains separate for display purposes.
5. Under **Inventory → Project approvals**, managers can approve or reject pending receipts and transfers. Each affected project requires its own approval. A project-to-project transfer needs both source and destination managers; a project-office movement needs the affected project's manager.

## Workflow and protections

- New project receipts are **pending**. No stock record or movement is created until approval; office-only receipts remain immediate.
- Project-related stock transfers are **pending** and do not alter the source or destination balances. Office-to-office transfers remain immediate.
- Rejection requires a reason and leaves balances untouched. The requester cannot approve their own transaction. The decision is project-assignment- and access-profile-checked on every request.
- Final approval rechecks the original requester's live authority, company/project scopes, active records, unit precision and available quantity, and posts in an atomic database transaction. If posting is not possible, nothing is applied; the last approval is rolled back for review.
- Submissions and decisions are recorded in the immutable company audit log. Duplicate submissions are idempotent by company + request type + UUID.
- Project **opening-stock Excel imports** are deliberately blocked from bypassing approval until a dedicated bulk-approval importer is built. Office-only opening-stock imports and zero-quantity legacy catalog records continue to use their existing flow.

## Unit rules and legacy data

- **Integer-only** by default for new units. The migration marks existing known *Piece/pc/pcs, Nos, Each, Unit, Set, Box, Bag, Pair, Roll, Pack, Kit* units as integer-only if their **current balances and minimums are whole numbers**.
- **Fractional allowed** for known measurable units such as kg, g, m, m², m³, L, and tonnes.
- Existing countable units with fractional current balances/minimums stay fractional temporarily, and appear in `audit_quantity_units` for manual review. Changing them to integer-only is blocked until these current quantities are reconciled. **Historical movement and transfer records are not modified or rounded.**
- Whole quantities now display without `.000`, including `10` and `100`.

## Checks

`python manage.py check`

`python manage.py makemigrations --check --dry-run`

`python manage.py test apps.inventory.tests.test_project_stock_approvals`

`python manage.py audit_quantity_units`

**Operational note:** Existing projects do not receive a made-up project manager during the migration. Assign a valid approver to each active project before submitting new requests. Production validation, migrations, and integration tests must be run in a configured Django environment with the production database adapter installed.

## Production preflight hotfix (2026-11-12)

The original `verify-granular-access-authority.py` and the Subcontractor
release gate were still enforcing a **96-key live catalog** even though the
new `inventory.stock.approve` permission correctly expanded it to **97**.
The hotfix keeps the frozen **94 historical keys** and the two approved
Subcontractor keys unchanged, fingerprints the prior **96-key** catalog, and
permits **only** the approved Project Inventory permission as the 97th key.
It also verifies that the existing 0013 database constraint remains the
original 96-key snapshot and migration 0016 installs exactly the 97-key
constraint before seeding the restricted manager profile.

Verification from source directory:

```sh
python3 scripts/verify-granular-access-authority.py
python3 scripts/verify-subcontractor-release-extension.py
python3 scripts/verify-project-inventory-approval-extension.py
bash scripts/verify-production-freeze.sh
```

Then deploy using the existing `sudo bash ./scripts/deploy-production.sh`.
Keep the original database and media volumes; replace application source
only. Do not skip the production preflight or manually insert grants.
