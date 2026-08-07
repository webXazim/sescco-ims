# Validation report

## Static validation completed in this build environment

- Python source compilation with `python -m compileall`;
- JavaScript syntax validation with Node.js;
- shell syntax validation for every deployment and maintenance script;
- Compose YAML parsing, including anchors and the shared-proxy override;
- Nginx syntax validation with temporary local upstream/certificate fixtures;
- route/template/static reference checks;
- migration/model field consistency checks;
- archive path and checksum validation;
- XLSX/XLSM structure, traversal and expanded-size safety checks;
- 111 included Django test methods across access, inventory, filtering, exports, imports, and operations.

## Runtime limitation

The available package mirror did not provide the pinned Django distribution, so
Django's runtime test runner could not be executed in this container. The full
test suite remains included in the release and must be run in Docker or CI:

```bash
docker compose --env-file .env.production build ims_web
docker compose --env-file .env.production run --rm \
  -e RUN_STARTUP_TASKS=0 ims_web python manage.py test
```

Before production traffic, also run:

```bash
./scripts/preflight.sh
./scripts/manage.sh check --deploy
./scripts/manage.sh makemigrations --check --dry-run
```

The deployment script runs the two Django deployment checks automatically after
the healthy service starts.
