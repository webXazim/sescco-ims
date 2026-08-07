# Operations guide

## Status

```bash
docker compose --env-file .env.production ps
docker compose --env-file .env.production logs -f --tail=150 ims_web
docker compose --env-file .env.production logs -f --tail=150 ims_gateway
```

## Health

```bash
curl -H 'Host: ims.a2tdev.com' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8087/app/health/live/
curl -H 'Host: ims.a2tdev.com' -H 'X-Forwarded-Proto: https' \
  http://127.0.0.1:8087/app/health/ready/
```

Liveness confirms that Django is running. Readiness also confirms PostgreSQL
connectivity.

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
./scripts/deploy-production.sh
```

## Static files return 403

Static files are served by `ims_gateway` from the `ims_static_data` volume. If
the page renders as unstyled HTML and browser requests below `/static/` return
403, rebuild and recreate the web container so `collectstatic` applies the
public static-file permissions:

```bash
docker compose --env-file .env.production build ims_web
docker compose --env-file .env.production up -d --force-recreate ims_web
docker compose --env-file .env.production restart ims_gateway
curl -I https://ims.a2tdev.com/static/css/styles.css
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
