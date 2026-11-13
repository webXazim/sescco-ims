# SESCCO IMS v1.0.127 — Production deployment compatibility hotfix

## Root cause

v1.0.127 extends v1.0.117 with Project Pulse and 124 permissions. The production deployment scripts still ran historical frozen release verifiers which insist that the current `VERSION` file remains at `1.0.117` and the access catalog has exactly 97 permissions. These assumptions no longer hold, although the historical contracts must remain immutable.

## Changes

- Add `scripts/verify-current-release.py`, checking v1.0.127, 124 permissions, 27 Pulse permissions, latest access-constraint migration, private receipt storage and preserved production/security boundaries.
- Replace direct deployment use of the historical 1.0.117 static verifier battery with the current-release verifier, immutable migration hash check, infrastructure, Payroll asset/authorization, branding and other production-freeze checks. Keep the historical verifier sources intact for historical release provenance.
- Preserve the original frozen platform-shell fingerprints for unchanged assets; use the separately approved current-release SHA256 manifest for the two modified Project Pulse shell files.
- Keep frozen Payroll frontend asset SHA256 checks, namespace checks, live route contracts, and current-compatible supplier-document checks. Synchronize Payroll cache tags with packaged version.
- In release tasks, run Project Pulse Django tests in a fresh test database before replacing the live web container; preserve all existing Django migration, company access, sourcing security, and financial reconciliation gates.
- Add a fail-fast preflight check if production `.env.production` APP_VERSION is defined but does not match the package version.

No database migration changes. No change to app financial formulas or Inventory/Payroll source behavior. The full package preserves the v1.0.127 application.

## Offline verification performed

- `bash scripts/verify-production-freeze.sh`: PASSED (current-release verifier + preserved relevant static gates)
- `bash scripts/verify-merge-baseline.sh`: PASSED (immutable migration hashes)
- `python scripts/project_pulse_u10_offline_checks.py`: PASSED (source, routes, permissions, PDF/XLSX smoke tests)
- Bash syntax, Python AST syntax, archive integrity: PASSED

## Not run here

Docker, Django/PostgreSQL migration and integration tests, and browser workflows. Run on staging before live rollout.

## Install patch on existing v1.0.127 checkout

Unzip the small patch outside `/opt/sites/ims`, then copy *only* its contents from the `sescco-ims/` folder to the existing checkout. Keep `.env.production`, secrets, git metadata and persistent volumes untouched. Verify the patch and commit source changes if the production preflight expects a clean Git tree.

```bash
cd /opt/sites/ims
bash scripts/verify-production-freeze.sh
# Verify APP_VERSION=1.0.127 in .env.production
sudo bash ./scripts/deploy-production.sh
```

Do not set the package VERSION back to 1.0.117, disable the freeze checks, or remove Project Pulse permission entries.
