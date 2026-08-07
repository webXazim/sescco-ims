# Upgrade 1 — Foundation and access control

Implemented:

- Django 5.2.17 LTS project structure with split development/production settings.
- Custom user model with Administrator and Storekeeper roles.
- Secure login, POST-only logout, and role-based home routing.
- Django admin reserved for staff/superusers.
- Storekeeper workspace routes for all approved prototype pages.
- Responsive shell adapted from the approved HTML/CSS prototype.
- PostgreSQL/Docker/Nginx production baseline.
- Initial authentication and route tests.

Deliberately deferred:

- Project, stock item and movement models (Upgrade 2/3).
- Real dashboard counters and operational forms.
- Search, export and workbook migration.
