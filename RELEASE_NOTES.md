# Project Inventory 1.0.0

This release completes the seven planned build upgrades and is prepared for an
isolated production deployment at `ims.a2tdev.com` beside other Docker Compose
projects.

## Included

- project-specific stock identity and immutable inventory movements;
- complete storekeeper workspace and administrator controls;
- advanced date, field and activity filtering with saved views;
- exact filtered XLSX/CSV export and protected Excel imports;
- rootless Django container, PostgreSQL, internal Nginx gateway and health checks;
- unique `ims` services, networks and persistent volumes;
- loopback or shared-proxy deployment options;
- pre-deployment backups, checksum-verified restore and operational guides;
- JSON logging, request IDs, secure production settings and workbook hardening.

## Deployment target

Follow `docs/DEPLOYMENT_IMS_A2TDEV.md`. Before traffic is enabled, complete every
item in `docs/RELEASE_CHECKLIST.md`, including the Docker/CI runtime test suite
and an isolated restore test.
