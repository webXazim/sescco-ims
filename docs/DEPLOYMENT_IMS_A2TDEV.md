# Deploying beside another Docker project

Target domain: `ims.a2tdev.com`

This deployment intentionally does not bind Docker directly to public ports 80
or 443. The IMS gateway listens only on `127.0.0.1:8087`; the existing host
Nginx routes the domain to it. Other Compose projects remain isolated.

## 1. DNS

Create an `A` record for `ims.a2tdev.com` pointing to the VPS public IPv4
address. When Cloudflare proxying is used, keep SSL/TLS mode at Full (strict)
after the origin certificate is installed.

## 2. Prepare the project

```bash
cd /opt
sudo mkdir -p inventory-management-system
sudo chown "$USER":"$USER" inventory-management-system
cd inventory-management-system
# Extract the release here.
cp .env.production.example .env.production
chmod 600 .env.production
```

Generate independent secrets instead of reusing values from the other project:

```bash
python3 - <<'PY'
import secrets
print("DJANGO_SECRET_KEY=" + secrets.token_urlsafe(64))
print("POSTGRES_PASSWORD=" + secrets.token_urlsafe(48))
PY
```

Put those values in `.env.production`. The supplied defaults already include:

```text
DJANGO_ALLOWED_HOSTS=ims.a2tdev.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://ims.a2tdev.com
IMS_HTTP_PORT=8087
```

## 3. First deployment

```bash
./scripts/deploy-production.sh
./scripts/create-admin.sh
```

The deployment script:

1. validates the environment and Compose file;
2. builds only the IMS image;
3. starts only the isolated IMS database;
4. creates a pre-deployment backup;
5. starts or updates IMS services;
6. waits for health checks;
7. runs Django deployment and migration-drift checks;
8. smoke-tests the local origin.

It does not stop or rebuild another project.

## 4. Host Nginx and TLS

Install the HTTP-only bootstrap virtual host first:

```bash
sudo mkdir -p /var/www/certbot
sudo cp deploy/host-nginx/ims.a2tdev.com.bootstrap.conf \
  /etc/nginx/sites-available/ims.a2tdev.com
sudo ln -s /etc/nginx/sites-available/ims.a2tdev.com \
  /etc/nginx/sites-enabled/ims.a2tdev.com
sudo nginx -t
sudo systemctl reload nginx
```

Request the certificate, then replace the bootstrap file with the final HTTPS
configuration:

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d ims.a2tdev.com
sudo cp deploy/host-nginx/ims.a2tdev.com.conf \
  /etc/nginx/sites-available/ims.a2tdev.com
sudo nginx -t
sudo systemctl reload nginx
```

Verify:

```bash
curl -I https://ims.a2tdev.com/login/
curl https://ims.a2tdev.com/app/health/ready/
```

## 5. Existing Docker reverse proxy instead of host Nginx

When the other project uses Nginx Proxy Manager, Traefik, or another proxy
container, connect IMS to that proxy's existing external network:

Set these values in `.env.production` so routine deployments keep the same
network attachment:

```text
IMS_USE_SHARED_PROXY=1
IMS_PROXY_NETWORK=the_existing_proxy_network
```

Then deploy normally:

```bash
./scripts/deploy-production.sh
```

The proxy can reach the upstream at:

```text
ims-gateway:8080
```

Set the external hostname to `ims.a2tdev.com`, pass the original Host header,
and pass `X-Forwarded-Proto: https`.

## 6. Routine updates

Replace the source with the new release and run:

```bash
./scripts/deploy-production.sh
```

Never use `docker compose down -v`; that removes persistent data. Do not run
Docker-wide prune commands as part of an application deployment.
