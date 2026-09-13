# Release checklist

- [ ] `.env.production` contains no placeholders and is mode 600.
- [ ] Required secrets were generated independently with `scripts/create-production-env.sh` (or an equivalent cryptographically secure process).
- [ ] `./scripts/preflight.sh` passes.
- [ ] `PAYROLL_FIELD_ENCRYPTION_KEY` is stored in an independent protected disaster-recovery secret store.
- [ ] `DJANGO_TRUSTED_PROXY_IPS` includes the confirmed `ims_edge` subnet `172.20.0.0/16`.
- [ ] `./scripts/verify-production-infrastructure.sh` passes.
- [ ] `./scripts/verify-production-freeze.sh` passes.
- [ ] Production cutover uses the canonical `./scripts/deploy-production.sh` entrypoint, which verifies the packaged production freeze itself.
- [ ] A current production backup has passed `./scripts/rehearse-production-freeze.sh`.
- [ ] Rehearsal evidence contains successful row-count preservation, legacy field-data fingerprint preservation, and SHA-256 checksums.
- [ ] `/app/health/ready/` reports both `database=ready` and `migrations=ready`.
- [ ] Backup manifest contains `payroll_field_key_fingerprint_sha256` and a restore with the wrong key is rejected.
- [ ] Inventory, shared-shell, and Payroll static smoke-test URLs return 200 after deploy.
- [ ] Python compilation and static validation pass.
- [ ] `python manage.py test` passes in Docker or CI.
- [ ] `python manage.py check --deploy` passes.
- [ ] `makemigrations --check --dry-run` reports no drift.
- [ ] A pre-release database and media backup exists.
- [ ] `ims.sescco.com` DNS resolves to the correct VPS.
- [ ] TLS certificate is valid and HTTPS redirect works.
- [ ] Login, add stock, use stock, filtering and exact export are smoke-tested.
- [ ] Storekeeper cannot access `/admin/`.
- [ ] Private attachment URLs require authentication.
- [ ] Backup checksum verification passes.
- [ ] A restore test has been completed in an isolated environment.

## Final production freeze / release candidate (1.0.64)

- Run `python3 scripts/verify-release-candidate.py` and `./scripts/verify-production-freeze.sh` against the exact packaged source tree.
- Confirm `VERSION` is `1.0.64` and the Payroll static cache-busters are `1.0.64`.
- Confirm the predecessor artifact SHA-256 is `8291351ac88c883796d899f31fbffbb32416b79f53e1ad8be1d3485fd0049d9e` for `sescco-ims-1.0.63-full-payroll-production-e2e-certification.zip`.
- Do not add features, schema changes or Payroll formula changes after the final freeze is generated. Any such change requires a new release/version.
- Before production cutover, run the isolated rehearsal so deployment checks, zero migration drift, curated Payroll E2E tests and the full Django suite produce runtime evidence.

## Payroll production E2E certification (1.0.63)

- Run `python3 scripts/verify-payroll-production-e2e.py` before image build.
- In an environment with Django/PostgreSQL available, run `bash scripts/certify-payroll-production-e2e.sh` against an isolated test database.
- Production rehearsal must retain `payroll-e2e-certification.txt` alongside the other migration/reconciliation evidence.
- Do not certify the final release from static checks alone; the dedicated Django suite must pass in the release/rehearsal environment.
