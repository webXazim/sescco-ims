# Release checklist

- [ ] `.env.production` contains no placeholders and is mode 600.
- [ ] `./scripts/preflight.sh` passes.
- [ ] Python compilation and static validation pass.
- [ ] `python manage.py test` passes in Docker or CI.
- [ ] `python manage.py check --deploy` passes.
- [ ] `makemigrations --check --dry-run` reports no drift.
- [ ] A pre-release database and media backup exists.
- [ ] `ims.a2tdev.com` DNS resolves to the correct VPS.
- [ ] TLS certificate is valid and HTTPS redirect works.
- [ ] Login, add stock, use stock, filtering and exact export are smoke-tested.
- [ ] Storekeeper cannot access `/admin/`.
- [ ] Private attachment URLs require authentication.
- [ ] Backup checksum verification passes.
- [ ] A restore test has been completed in an isolated environment.
