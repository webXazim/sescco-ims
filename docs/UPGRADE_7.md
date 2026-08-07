# Upgrade 7 — production hardening and deployment

Upgrade 7 completes the first production release.

## Completed

- isolated Compose project name, service names, networks and persistent volume names;
- loopback-only Docker gateway on port `8087`, avoiding public-port conflicts;
- deployment target `https://ims.a2tdev.com`;
- optional shared Docker reverse-proxy network override persisted in the environment;
- strong production environment validation;
- database settings that safely accept passwords containing URL-reserved characters;
- two-stage rootless application image and `.dockerignore` secret protection;
- Gunicorn lifecycle, recycling and graceful shutdown settings;
- liveness, readiness and gateway health endpoints;
- request correlation IDs and structured JSON application logs;
- preserved HTTPS forwarding across the host and container proxy layers;
- secure cookies, HSTS, upload limits, hashed static assets and file permissions;
- pinned production dependencies and hardened workbook archive/XML parsing;
- pre-deployment database and private-media backups;
- checksum-verified database and media restore workflow;
- deployment locking, health waits, smoke testing and Django deploy checks;
- host Nginx configuration for `ims.a2tdev.com` with login throttling;
- operator, administrator, storekeeper, security and release documentation.

## Isolation guarantee

The production scripts use only the `ims` Compose project and services named
`ims_db`, `ims_web`, `ims_gateway`, and `ims_tools`. They never run global Docker
cleanup commands and never call `docker compose down -v`.

The database and uploads use these explicit volumes:

- `ims_postgres_data`
- `ims_media_data`
- `ims_static_data`

The public origin is reached through `127.0.0.1:8087`, so another project can
continue using ports 80 and 443 through the existing host reverse proxy.
