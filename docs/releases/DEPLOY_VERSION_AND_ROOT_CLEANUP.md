# SESCCO IMS 1.0.127 — environment version sync and clean project root

## Cause
The server keeps a private `.env.production` file (never included in source ZIPs). It still has `APP_VERSION=1.0.0` while `VERSION` in the current package is `1.0.127`. The preflight correctly refuses a mismatch. Do not change the release VERSION, recreate the `.env.production` from its example, or regenerate encryption keys.

## Applying the files on the existing Ubuntu server

1. Back up the server source and environment, and use the included patch or full package to update `/opt/sites/ims` without replacing `.env.production`, PostgreSQL, or private uploads.
2. From `/opt/sites/ims`, run:

```bash
sudo python3 scripts/sync-production-app-version.py --apply
sudo bash scripts/clean-project-root.sh
python3 scripts/sync-production-app-version.py --check
sudo bash scripts/verify-production-freeze.sh
```

The version sync updates only `APP_VERSION`; it makes a restricted backup of the original environment in `.secrets/env-backups/` (never exposed in the ZIP). The root cleaner moves exactly the known old note/changelog names out of the top level; clean copies are in `docs/releases/`. If a server copy differs, it is backed up under `.secrets/root-note-backups/` before removal. It is safe to repeat either command.

3. Inspect `git status --short` and review changes carefully. The production deployment preflight requires a **clean Git working tree**, so commit the intended source/document cleanup changes using your existing release Git workflow. Do not accidentally commit unrelated files or production secrets. `.env.production` and `.secrets/` are git-ignored.
4. After staging checks, run:

```bash
sudo bash scripts/deploy-production.sh
```

Future runs of `deploy-production.sh` automatically synchronize the one public version label with the checked-out `VERSION` before validation; all other production settings, credentials, and secrets are left untouched. Source and migration/security checks remain enforced.

## Directory layout after cleanup

The root contains the essential application and deployment files (`manage.py`, `Dockerfile`, `VERSION`, `README.md`, `RELEASE_NOTES.md`, `deploy.md`, `docker-compose*.yml`, `pyproject.toml`, `.env.production.example`) and the application folders (`apps/`, `config/`, `scripts/`, `templates/`, `static/`, `docs/`, etc.). Old release-specific Markdown and text notes live in `docs/releases/project-pulse/` or `docs/releases/legacy/`.

`RELEASE_NOTES.md` must remain in the top level because legacy validation scripts read it. Do not remove migrations, application configs, documentation referenced by verification scripts, or private deployment data. This package does not execute a production deployment or database migration on your behalf.
