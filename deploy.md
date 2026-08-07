The IMS release is production-ready and isolated from SESCCO:

- SESCCO: `127.0.0.1:8081`
- IMS: `127.0.0.1:8087`
- Separate PostgreSQL database and volume
- Separate media/static volumes and Docker networks
- Host Nginx owns public ports `80/443`
- Standard inventory units seed automatically
- Projects, users, and inventory start empty

Replace `YOUR_REAL_EMAIL` below.

## 1. Create the Cloudflare DNS record

In Cloudflare for `a2tdev.com`, add:

```text
Type: A
Name: ims
IPv4: 31.70.114.86
Proxy status: DNS only
TTL: Auto
```

Keep it DNS-only until the TLS certificate is installed.

Verify:

```sh
dig +short ims.a2tdev.com
```

Expected:

```text
31.70.114.86
```

## 2. Verify the project location

Connect:

```sh
ssh deploy@31.70.114.86
```

Check:

```sh
cd /opt/sites/ims
pwd
ls -la
```

You must see:

```text
docker-compose.yml
Dockerfile
manage.py
scripts/
deploy/
nginx/
```

Confirm the root is correct:

```sh
test -f docker-compose.yml && echo "IMS project root is correct"
```

If this message does not appear, the archive may have created a nested directory. Locate it:

```sh
find /opt/sites/ims -maxdepth 2 -name docker-compose.yml -print
```

Then `cd` to the directory containing `docker-compose.yml`.

## 3. Set ownership

```sh
sudo chown -R deploy:deploy /opt/sites/ims
cd /opt/sites/ims
```

## 4. Check that port 8087 is available

```sh
sudo ss -lntp | grep ':8087' || echo "Port 8087 is available"
```

If it reports only “available,” continue.

Check existing Docker projects:

```sh
sudo docker compose ls
```

## 5. Create the production environment

```sh
cd /opt/sites/ims
cp .env.production.example .env.production
chmod 600 .env.production
```

Generate secure secrets:

```sh
DJANGO_SECRET=$(openssl rand -hex 64)
DATABASE_PASSWORD=$(openssl rand -hex 48)

sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=${DJANGO_SECRET}|" .env.production
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${DATABASE_PASSWORD}|" .env.production

unset DJANGO_SECRET
unset DATABASE_PASSWORD
```

Confirm no placeholders remain:

```sh
if grep -nE 'replace-with|development-only|changeme|example-password' .env.production; then
    echo "ERROR: Placeholder values remain"
else
    echo "Production secrets are configured"
fi
```

Review the non-secret deployment values:

```sh
grep -E '^(COMPOSE_PROJECT_NAME|IMS_HTTP_PORT|IMS_USE_SHARED_PROXY|DJANGO_ALLOWED_HOSTS|DJANGO_CSRF_TRUSTED_ORIGINS|POSTGRES_DB|POSTGRES_USER)=' .env.production
```

Expected:

```env
COMPOSE_PROJECT_NAME=ims
IMS_HTTP_PORT=8087
IMS_USE_SHARED_PROXY=0
DJANGO_ALLOWED_HOSTS=ims.a2tdev.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://ims.a2tdev.com
POSTGRES_DB=ims_inventory
POSTGRES_USER=ims_inventory
```

## 6. Make scripts executable

```sh
chmod +x scripts/*.sh
chmod +x scripts/lib/*.sh
```

## 7. Run the preflight validation

```sh
sudo ./scripts/preflight.sh
```

Expected final message:

```text
Preflight passed
```

## 8. Deploy IMS

```sh
sudo ./scripts/deploy-production.sh
```

This will:

- Build the IMS image
- Start its isolated PostgreSQL
- Apply migrations
- Seed common inventory units
- Collect static files
- Start Gunicorn and the IMS gateway
- Run production checks
- Test the local health endpoint

It will not restart, stop, or modify SESCCO.

## 9. Check IMS containers

```sh
sudo docker compose --env-file .env.production ps
```

Expected services:

```text
ims-db
ims-web
ims-gateway
```

They should all be running and healthy.

Check both projects:

```sh
sudo docker compose ls
```

Check IMS logs:

```sh
sudo docker compose --env-file .env.production logs --tail=100 ims_db
sudo docker compose --env-file .env.production logs --tail=100 ims_web
sudo docker compose --env-file .env.production logs --tail=100 ims_gateway
```

## 10. Test IMS internally

```sh
curl -i \
  -H "Host: ims.a2tdev.com" \
  -H "X-Forwarded-Proto: https" \
  http://127.0.0.1:8087/app/health/ready/
```

Expected:

```json
{"status":"ok","service":"inventory","version":"1.0.0","database":"ready"}
```

Confirm the port is loopback-only:

```sh
sudo ss -lntp | grep ':8087'
```

Expected binding:

```text
127.0.0.1:8087
```

## 11. Install the temporary Nginx configuration

```sh
cd /opt/sites/ims

sudo mkdir -p /var/www/certbot

sudo cp \
  deploy/host-nginx/ims.a2tdev.com.bootstrap.conf \
  /etc/nginx/sites-available/ims.a2tdev.com

sudo ln -sfn \
  /etc/nginx/sites-available/ims.a2tdev.com \
  /etc/nginx/sites-enabled/ims.a2tdev.com
```

Validate and reload:

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status nginx --no-pager
```

Test HTTP:

```sh
curl -I http://ims.a2tdev.com/login/
```

A redirect to HTTPS is acceptable.

## 12. Obtain the TLS certificate

Cloudflare must still be DNS-only.

```sh
sudo certbot certonly \
  --webroot \
  -w /var/www/certbot \
  -d ims.a2tdev.com \
  --agree-tos \
  --email YOUR_REAL_EMAIL \
  --no-eff-email
```

Confirm the certificate:

```sh
sudo certbot certificates
```

## 13. Install the final HTTPS configuration

```sh
cd /opt/sites/ims

sudo cp \
  deploy/host-nginx/ims.a2tdev.com.conf \
  /etc/nginx/sites-available/ims.a2tdev.com

sudo nginx -t
sudo systemctl reload nginx
```

Confirm Nginx is listening:

```sh
sudo ss -lntp | grep -E ':(80|443)\b'
```

## 14. Test IMS publicly

```sh
curl -I https://ims.a2tdev.com/login/
curl -fsS https://ims.a2tdev.com/app/health/ready/
```

Expected health result:

```json
{"status":"ok","service":"inventory","version":"1.0.0","database":"ready"}
```

Open:

```text
https://ims.a2tdev.com/login/
```

Test certificate renewal:

```sh
sudo certbot renew --dry-run
```

## 15. Enable Cloudflare proxy

After direct HTTPS works:

1. Change `ims.a2tdev.com` to **Proxied**—orange cloud.
2. Click Save.
3. Ensure Cloudflare SSL/TLS mode is **Full (strict)**.
4. Wait several minutes.

Cloudflare recommends proxying web records and using Full (strict) when the origin has a valid certificate. [Cloudflare proxy documentation](https://developers.cloudflare.com/dns/proxy-status/), [Full (strict) documentation](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/)

Test again:

```sh
curl -I https://ims.a2tdev.com/login/
curl -fsS https://ims.a2tdev.com/app/health/ready/
```

## 16. Create the IMS administrator

```sh
cd /opt/sites/ims
sudo ./scripts/create-admin.sh
```

Enter the administrator username, email, and password.

Then sign in:

```text
https://ims.a2tdev.com/admin/
```

Operational users can subsequently be created with the `Storekeeper` role.

## 17. Create and verify the first backup

```sh
cd /opt/sites/ims
sudo ./scripts/backup.sh
sudo find backups -maxdepth 2 -type f -ls
```

A complete backup includes:

```text
database.dump
media.tar.gz
manifest.txt
SHA256SUMS
```

## 18. Add an automatic daily backup

Open root’s crontab:

```sh
sudo crontab -e
```

Add:

```cron
20 2 * * * cd /opt/sites/ims && ./scripts/backup.sh >> /var/log/ims-backup.log 2>&1
```

Backups are retained for 30 days by default. Also copy them to off-VPS storage.

## 19. Routine updates

When uploading a new IMS release, preserve:

```text
.env.production
backups/
```

Then run:

```sh
cd /opt/sites/ims
sudo ./scripts/deploy-production.sh
```

## 20. Useful IMS commands

```sh
cd /opt/sites/ims

# Status
sudo docker compose --env-file .env.production ps

# Follow logs
sudo docker compose --env-file .env.production logs -f --tail=150 ims_web ims_gateway

# Django checks
sudo ./scripts/manage.sh check
sudo ./scripts/manage.sh showmigrations

# Create another administrator
sudo ./scripts/create-admin.sh

# Backup
sudo ./scripts/backup.sh

# Restart only IMS application services
sudo docker compose --env-file .env.production restart ims_web ims_gateway

# Local readiness test
curl -H "Host: ims.a2tdev.com" \
     -H "X-Forwarded-Proto: https" \
     http://127.0.0.1:8087/app/health/ready/
```

Never run:

```sh
docker compose down -v
docker system prune --volumes
```

Those commands could destroy persistent data.