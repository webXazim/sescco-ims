# 1.0.117 — Django Index Name Deployment Hotfix

Django validates explicit model index names at a maximum of 30 characters. The 1.0.111 deployment check exposed two carried-forward model indexes above that limit:

- `accounts.AccessProfile`: `acct_profile_company_active_idx` (31) → `acct_prof_company_active_idx` (28)
- `sourcing.SourcingManpowerContact`: `src_mpcontact_supplier_active_idx` (33) → `src_mpc_supplier_active_idx` (27)

The historical migrations are intentionally left unchanged. Two forward `RenameIndex` migrations preserve migration lineage and safely handle both an already-migrated database and a fresh database that applies the historical index before the rename.

This hotfix does not change business data, Payroll calculations, Inventory quantities, Sourcing permissions, Sourcing business behavior, or operational-module relationships.

The production gate that originally failed is authoritative after this hotfix:

`python manage.py check --deploy --fail-level ERROR`

`security.W021` for `SECURE_HSTS_PRELOAD` remains a warning only. Enabling HSTS preload is an independent infrastructure decision and should be done only after every applicable HTTPS/subdomain requirement is intentionally satisfied.
