# SESCCO IMS v1.0.125 — Project Pulse U08

## Scope: Contract value, variations, financial forecasts and confidentiality

**Build basis:** U07 full application (`SESCCO_IMS_Project_Pulse_U07_v1.0.124_Full.zip`). This is a full updated source archive, not a patch.

### Features added

- **Dedicated owner-restricted Project Pulse financials** for every existing project, opened from that project's overview. Project identifiers are not duplicated.
- **Base contract value** is the full approved amount in SAR, excluding recoverable VAT. Proposals require approval; the previous approved value remains effective until a new one is approved. Prior revisions remain immutable.
- **Signed variations** support additions (+) and deductions (−), descriptions, reference and reason. Only approved variations change revised contract value. Deductions cannot reduce the revised contract below zero.
- **Estimated cost to complete** supports approved revisions with effective date and reason. At approval the system takes an immutable snapshot of approved actual task expenses, and stores the estimate of *remaining* expenses.
- **Financial calculations:** revised contract = latest approved base contract + signed approved variations; forecast final cost = approved expense baseline at the approved forecast + forecast remaining cost; forecast final profit or loss = revised contract − forecast final cost; margin = forecast profit / revised contract × 100 (undefined if contract is zero). Planned profit = revised contract − fully approved category budgets (only when budget coverage is complete).
- **Stale forecast warnings:** displayed when the latest approved expense total differs from the approved cost baseline, or when an approved contract revision/variation occurred since the forecast. The historical forecast is not silently recalculated using changed data.
- **New customizable permissions** (`pulse.financials.view`, `pulse.contracts.manage`, `pulse.contracts.approve`, `pulse.forecasts.manage`, `pulse.forecasts.approve`). Granted to built-in Owner access profiles via migration, but not automatically to finance, project or inventory managers. Profiles still require the underlying project/expense/budget viewing permissions and project scope.
- **Approval controls:** non-owners cannot approve their own contract, variation or forecast submissions. Rejections require a reason, submissions and approvals are audit logged with confidential amount and reason fields omitted from general audit log entries.
- **Financial history:** proposed, approved and rejected commercial records are retained and cannot be edited or deleted. Archive/closed projects permit viewing but no financial changes.
- **No integration** with Inventory or Payroll; expense figures are from the standalone Project Pulse expense approval workflow.

### Important financial limitations

This U08 dashboard estimates **forecast final project profit**, not **realized/earned accounting profit**. Revenue recognition, invoicing, received client payments, accounts payable, corporate overheads, income tax and statutory tax accounting are not represented in this release. Contract and expense values are treated as **exclusive of recoverable VAT**; users are responsible for entering consistent values. An approved forecast can become stale after scope or actual cost changes and must be revised by an authorized user.

Profit is intentionally **not displayed** if the approved base contract or approved cost-to-complete forecast is missing. An approved zero contract produces an undefined margin rather than a fabricated percentage. Budgets with missing active categories yield no planned-profit figure.

### Changes

- `apps/project_pulse/models.py` — `PulseContractRevision`, `PulseContractVariation`, `PulseCostForecast`, common approval base.
- `apps/project_pulse/commercial_services.py` — scoped financial services and calculation rules.
- `apps/project_pulse/views.py`, `urls.py`, `forms.py`, `access.py` — new pages and protected actions.
- `templates/project_pulse/financials.html`, `financial_propose.html`, `project_detail.html`, `sidebar.html`, `base.html` — confidential UI integration.
- `apps/accounts/access_catalog.py`, `access_profiles.py` and `migrations/0024_project_pulse_u08_commercial_authority.py` — new access profiles and database permission constraints.
- `apps/project_pulse/migrations/0007_commercial_forecasts.py` — schema migration.
- `apps/project_pulse/tests/test_commercials.py` — regression test cases.
- `.env.production.example` — `APP_VERSION=1.0.125`.

### Installation / staging checks

1. Back up application, database and the **private Project Pulse receipts volume**.
2. Deploy the full updated application source in staging. Retain environment secrets, database data and persistent volumes.
3. Set `APP_VERSION=1.0.125`.
4. Run in the configured Django environment:

```bash
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

5. Test Owner and custom profile access, own-submission approvals, cross-company isolation and financial calculations with representative sample projects. Restart application services once checks succeed.

### Validation status

This packaging environment does not have Django installed. Python syntax, registered URLs, permission/migration constants, release archive integrity and preservation of the U07 source are statically verifiable. **Django database migrations, runtime test suites and browser workflows remain unexecuted; U08 is not independently certified production-ready.**

### Next milestones

U09 reporting, filtering and secure exports; U10 full integration tests, security hardening and release readiness.
