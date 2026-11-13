# SESCCO Project Pulse — U02 Project Team Management

**Release:** 1.0.119 (November 12, 2026)  
**Base:** SESCCO_IMS_Project_Pulse_U01_v1.0.118_Full.zip  
**Progress:** 2 of 10 upgrades implemented at code level; staging verification pending.

## What's included

- Project Pulse team assignment page for each existing company project.
- One active Project Pulse manager per project, with multiple team members.
- Add an eligible user, change their role, replace the manager (the previous manager becomes a member), and remove/reactivate members.
- Team assignment does **not** grant app access: existing Access Profiles and company/project scopes remain the source of authority.
- Only active company users with Project Pulse overview/project access and a project scope including the selected project can be assigned.
- Independent of the `projects.Project.inventory_manager` Inventory approval field and the legacy `manager_name` field.
- Automatic protection of archived/completed project teams against changes.
- Audit events for additions, updates, removals and manager replacements.
- Database constraints for unique project+membership pairs and one active manager per project.
- Team-view and team-management permissions separately configurable in Administration > Access Profiles:
  - `pulse.team.view` (requires `pulse.projects.view`)
  - `pulse.team.manage` (requires `pulse.team.view`)
- Existing Company Owner system profiles receive the two U02 grants during migration; all other profiles are **opt-in**.
- Team summary visible on a project detail page only to authorized team viewers. Stale assignments are identified when a user loses access.
- Full updated source with no new Payroll/Inventory project expense integration.

## Recommended user workflow

1. Sign in as a Company Owner.
2. Use Project Pulse > Projects > [Project] > **Manage / view team**.
3. Select a currently authorized user and choose `Team member` or `Project manager`.
4. Save; to replace the manager, assign another authorized user as `Project manager`.
5. For non-owner managers who should administer teams, use Administration > Access Profiles to clone/customize the user's access profile and grant all four Project Pulse permissions (`overview.view`, `projects.view`, `team.view`, `team.manage`). Assign the customized profile to intended users and confirm their project scopes.
6. Do not expect assignment alone to grant Project Pulse access or Inventory stock approval ability.

## Deployment (after a database + source backup)

```bash
python manage.py migrate
python manage.py check
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

Restart application processes and test team assignment on a non-production project. Preserve existing `.env`, uploaded documents, and the production database. U01 → U02 migrations must be applied in order.

## Validations and known limits

Static Python compilation and archive integrity were performed. **Django isn't installed in the build container**, therefore live migration execution, Django tests, HTTP/CSRF behavior and DB-specific constraints are not yet runtime-verified here; run the included tests in a configured environment before production use.

U03 introduces work categories and tasks. U05 onward introduces independent task expenses, budgets and financial dashboards. **No new project financial data is stored or exposed in U02.**
