SESCCO IMS — recent project activity display patch

Changed files:
  templates/projects/project_detail.html
  static/css/styles.css

Behavior:
  * Material name and movement action/date appear on separate lines.
  * Shows the user who created each movement using existing created_by.
  * Older records without a user show "Unknown user".
  * No models, migrations, routes or database records changed.

Safe VPS deployment:
  1. Back up the two original files at the corresponding project paths.
  2. Copy the two replacement files into the existing app's same paths.
  3. Rebuild/redeploy the application using your EXISTING deployment process.
     Ensure static assets are updated (for Django, collectstatic when needed).
  4. Open a project detail page, verify attribution and mobile layout.
  5. On problems, restore those two backed-up files and redeploy.

IMPORTANT: Do not replace server .env files, volumes, database or user media.

Validation performed here: focused source assertions and git diff --check.
Django runtime tests could not run in this environment (Django not installed).
