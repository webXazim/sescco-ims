# SESCCO Project Pulse — U03 Work Categories & Task Management

**Release:** 1.0.120 (November 12, 2026)  
**Base:** `SESCCO_IMS_Project_Pulse_U02_v1.0.119_Full.zip`  
**Status:** Upgrade 3 of 10 built at code level; staging/runtime tests must still be run.

## New capabilities

- Create, edit, order, archive and restore **project work categories**, with unique normalized names per project and non-destructive archive.
- Create, edit, archive and restore **tasks** under categories; each has a title, description, responsible team member (optional), priority, status, planned start, due date and display order.
- Work category and task tables, project-level navigation, task search/category/status/archived filters, and **My Tasks** for currently assigned, authorized team members.
- Separate custom Access Profile grants: `pulse.categories.view`, `pulse.categories.manage`, `pulse.tasks.view`, `pulse.tasks.manage`.
- Current owner system profiles receive U03 grants during migration; other profiles are unchanged and must opt in.
- Only active Project Pulse team members with permission to view tasks may be task assignees. Assignments alone **never grant permissions**.
- All reads/writes enforce active company membership, project scope, and exact Pulse access grants. Work editing requires the shared project to have **Active** status; closed/on-hold projects are read-only.
- Category and task edits are atomic, validated, and logged in the existing audit register. Archiving a category requires its tasks to be archived first. The data is retained.
- No change to project inventory managers, stock transfers, payroll or sourcing logic. No financial records introduced.

## UI navigation

1. Project Pulse → **Projects** → open project.
2. **Work categories** → Add work category. Optionally edit its description and order.
3. **Tasks** → Add task; choose a category, title, assignee from the Project Pulse team, dates, priority and status.
4. **My Tasks** → currently assigned work across permitted projects.
5. Use **Archive** and **Restore** instead of deleting tasks or categories.

Task categories are project-specific. These are not **expense categories**: expense classifications and task expenses are reserved for **U05**. Work category budgets arrive in **U07**. U04 adds progress percentages, history and weighted completion.

## Deployment

Back up source and database first. Start from U02 or earlier and apply migrations sequentially:

```bash
python manage.py migrate
python manage.py check
python manage.py test apps.project_pulse
python manage.py collectstatic --noinput
```

Restart application processes. Keep your production `.env`, uploaded media and database; never overwrite them with sample files. Configure Access Profiles via Administration; grant task/category permissions explicitly to non-owner users, and verify their assigned project scopes. Then assign eligible people to the project through the U02 Team page.

## Verification performed

- Entire 679-Python-file source tree checked for Python syntax errors.
- All 15 Project Pulse URL handlers and their template references checked.
- 105 permission values matched between the access catalog and the U03 constraint migration.
- U03 automated Django tests were written for CRUD, project/company scoping, access restrictions, assignment checks, archive history and invalid inputs.
- Full archive was integrity-checked before delivery.

**Limitation:** Django 5.2.17 and the database service are unavailable in this sandbox (package download has no DNS connection), so Django's `manage.py check`, `migrate`, HTTP tests, and database tests have **not** been executed. They must pass in the configured deployment environment before production rollout.
