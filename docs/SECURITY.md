# Security controls

- No public registration exists.
- Storekeepers cannot enter Django admin.
- Stock balances change only through immutable movements.
- Negative stock and duplicate submissions are blocked.
- Uploaded files are private and never served directly by Nginx.
- Docker publishes only a loopback origin port.
- PostgreSQL is isolated on an internal Docker network.
- Production requires explicit allowed hosts, CSRF origins and a strong secret.
- Session and CSRF cookies are Secure, HttpOnly and SameSite=Lax.
- HTTPS redirect and HSTS are enabled.
- Static files use content-hashed names.
- Upload sizes and file permissions are restricted.
- Login requests are rate-limited in the supplied host Nginx configuration.
- Services use `no-new-privileges`; the Django container runs as a non-root user.
- Request IDs and JSON logs support incident investigation.
- Deployments create a backup before migrations and do not touch other projects.

## Production checklist

```bash
./scripts/preflight.sh
./scripts/manage.sh check --deploy
./scripts/manage.sh makemigrations --check --dry-run
```

Also verify firewall rules, operating-system updates, Nginx TLS configuration,
backup copies, and restoration tests.

## Workbook import protection

- Upload size is limited before preview.
- XLSX/XLSM ZIP structure is validated before OpenPyXL parses it.
- Unsafe internal paths, encrypted members, excessive member counts, oversized
  expanded content and unsafe compression ratios are rejected.
- External workbook links are not loaded.
- `defusedxml` is installed so OpenPyXL uses hardened XML parsing.
- Import confirmation remains atomic and administrator-only.
