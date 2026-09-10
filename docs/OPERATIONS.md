# Operations guide

## Status

```bash
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs -f --tail=150 ims_web
docker compose --env-file .env.production logs -f --tail=150 ims_gateway
```

## Health

```bash
curl -H 'Host: ims.sescco.com' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8087/app/health/live/
curl -H 'Host: ims.sescco.com' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8087/app/health/ready/
```

Liveness confirms that Django is running. Readiness confirms PostgreSQL connectivity **and** that the running release has no unapplied Django migrations.

## Django commands

```bash
./scripts/manage.sh check
./scripts/manage.sh showmigrations
./scripts/manage.sh shell
./scripts/create-admin.sh
```

## Restart only IMS

```bash
docker compose --env-file .env.production restart ims_web ims_gateway
```

## Update

```bash
./scripts/preflight.sh
./scripts/deploy-production.sh
```

Normal container restarts do not run migrations. Production migrations, merge reconciliation commands, and `collectstatic` run explicitly through `scripts/release-tasks.sh` during deploy/restore.

## Static files return 403

Static files are served by `ims_gateway` from the `ims_static_data` volume. Deployments retain previous hashed assets during the cutover so old and new web responses can coexist safely for the short promotion window. If
the page renders as unstyled HTML and browser requests below `/static/` return
403, deploy the current release. Startup runs `collectstatic` and repairs the
whole shared volume so directories retained from older releases are readable
by the separate Nginx container:

```bash
./scripts/deploy-production.sh
curl -I https://ims.sescco.com/static/css/styles.css
```

The CSS request should return `200`. Media upload permissions remain private;
do not make the media volume world-readable.

## Logs

Django writes structured JSON to container stdout. Every request receives an
`X-Request-ID`; the same value appears in application and Gunicorn access logs.
Use it to correlate a user-visible error with the server log.

Docker log rotation is configured per IMS service. It does not alter another
project's logging configuration.

## Capacity

The default Gunicorn configuration uses two workers and two threads to remain
modest on a VPS hosting another application. Increase workers only after
observing CPU, memory and response latency. PostgreSQL is not published to the
host or to the IMS edge network.
