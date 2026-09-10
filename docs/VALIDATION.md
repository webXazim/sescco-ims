# Validation report

## Upgrade 12 static validation completed in this build environment

The final merge artifact was checked statically before packaging:

- 288 Python source files parsed/compiled successfully;
- 320 statically discoverable Django test methods are present;
- JavaScript syntax validation passed for Inventory, Payroll and shared-platform bundles;
- shell syntax validation passed for every deployment/maintenance script, including the Upgrade 12 rehearsal and frozen-deploy wrapper;
- the base, shared-proxy and isolated-rehearsal Compose YAML files parse successfully;
- the internal Nginx gateway configuration passed `nginx -t` with a local upstream fixture;
- 38 Django migration nodes form an acyclic graph with no missing local dependencies;
- the immutable IMS/merge migration baseline verifier passes;
- the Payroll frontend verifier resolves 59 browser URL contracts against 61 Django routes and its frozen asset hashes pass;
- the unified platform-shell frozen asset verifier passes;
- the unchanged Upgrade 11 production-infrastructure contract and frozen asset hashes pass;
- Upgrade 12 row-count and legacy-field fingerprint comparators pass positive tests and reject injected drift;
- `git diff --check` passes;
- the final Upgrade 12 source/configuration freeze is verified by `scripts/verify-production-freeze.sh` after `merge/production-freeze.sha256` is generated.

## Required runtime rehearsal

The final runtime gate must use an actual PostgreSQL backup and Docker runtime. Before the first merged
production cutover, run:

```bash
./scripts/rehearse-production-freeze.sh /absolute/path/to/current-production-backup
```

The rehearsal restores only into `ims_merge_rehearsal_*` resources, applies the complete migration chain,
runs every merge reconciliation command, deployment/schema checks, static collection and the full Django
test suite. It then verifies both protected row counts and SHA-256 fingerprints of every pre-existing field
in the protected legacy IMS tables. New additive merge columns are deliberately excluded from that legacy
field fingerprint contract.

Evidence is written to `rehearsal-evidence/<UTC timestamp>/` unless another directory is supplied, and the
evidence files receive their own SHA-256 manifest.

After rehearsal passes, production cutover uses:

```bash
./scripts/verify-production-freeze.sh
./scripts/deploy-production.sh
```

The frozen deploy wrapper verifies Upgrade 12 first, then hands off to the unchanged Upgrade 11 deployment
pipeline, which runs its existing preflight, safety backup, migration/reconciliation/static release tasks,
web/gateway promotion, readiness check and static smoke tests.

## Build-environment limitation

This artifact-building container does not provide Docker or the project's pinned Django runtime, so the real
PostgreSQL restore/migration/test rehearsal cannot be truthfully claimed as executed here. Upgrade 12 ships
that executable isolated gate rather than substituting a SQLite or mocked result. Promote the production
freeze only after the rehearsal succeeds on CI/staging/VPS infrastructure using a current backup and the
correct long-lived `PAYROLL_FIELD_ENCRYPTION_KEY`.
