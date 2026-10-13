# SESCCO MS — Subcontractor & Services Directory
## Upgrade 01/10: Domain and database foundation

**Status:** Implementation prepared, awaiting Django checks and migration rehearsal inside the existing production-equivalent Docker image. Not a finished user-facing module.

### Included

- `SourcingSubcontractor`: company-scoped identity, contacts summary, address, service coverage, CR/VAT, active/inactive/archive/trash lifecycle, searchable normalized identity.
- `SourcingSubcontractorContact`: separate active and primary contact records with a uniqueness constraint for the active primary contact.
- `SourcingService`: company-scoped controlled service master with category, aliases, optional default rate unit, notes, and duplicate vocabulary validation.
- `SourcingSubcontractorService`: normalized company-owned service catalog relation, scope, location, availability, optional non-negative reference rate, rate basis, lead time, verification placeholders, active flag.
- `SourcingSubcontractorServiceRevision`: immutable revision history, snapshot identity and actor references; evidence survives offer deletion.
- An additive Sourcing migration `0010_subcontractor_service_foundation.py`, with explicit indexes, constraints, protected relations and compatible abstract foreign-key migration state.
- Foundation tests validating tenant isolation, normalization, duplicate rules, missing-price handling and immutability.

No existing Vendor/Manpower/Inventory/Payroll/Projects schema is changed. There are **no new navigable URLs, forms or visible directory pages** in this milestone; those arrive in Upgrades 02–05.

### Important release constraint

The existing 1.0.117 production-freeze checks strictly require 94 access permissions. Adding the two new Subcontractor permissions to this release without reissuing the established access-control release contracts causes the production release verifier to fail. Therefore, new permission definitions, profile migration, administration UI changes and the new route guards are intentionally deferred to Upgrade 03, which must also revise the permissions release contract. Upgrade 01 does not introduce publicly reachable endpoints or grant any new access.

### Validation in a disposable/staging Docker environment

Using the repository root, after reviewing the exact patch and ensuring the database is backed up:

```bash
# Static baseline / syntax checks
sha256sum -c merge/production-freeze.sha256
python -m compileall -q apps/sourcing
python scripts/verify-sourcing-domain-foundation.py
python scripts/verify-sourcing-security-certification.py

# Use the app container with its pinned Django dependencies and a STAGING database.
docker compose run --rm --no-deps ims_web python manage.py check --deploy --fail-level ERROR
docker compose run --rm --no-deps ims_web python manage.py makemigrations --check --dry-run
docker compose run --rm --no-deps ims_web python manage.py migrate --plan
docker compose run --rm --no-deps ims_web python manage.py test apps.sourcing.tests.test_subcontractor_foundation
```

Adapt `docker compose` to the project's `scripts/lib/compose.sh` wrapper and use its actual configured compose files; the commands above are illustrative. Do not run the migration command on production until the Docker checks, rollback/recovery plan, and database backup are confirmed. A migration plan does **not** execute migrations.

### Next upgrades

**02:** Full Services master selectors, forms, create/edit/status/delete services, audited lifecycle. **03:** Subcontractor CRUD, contacts, access profiles and navigation (including a versioned update to the frozen permissions contract). **04:** Service capabilities, reference rates and verification interfaces. **05–10:** Finder, history, documents, exchange, responsive integration and production certification.
