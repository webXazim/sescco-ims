# Move the existing IMS to ms.sescco.com

The new hostname routes through host Nginx to the existing IMS gateway at
`127.0.0.1:8087`. The company profile continues at `sescco.com`, on its existing
upstream. The Compose project remains `ims` with its existing database and volumes.

On 11 October 2026, the new DNS A record resolved to `31.70.114.86`. The company
site returned HTTP 200. The new IMS hostname had a certificate hostname mismatch
and returned HTTP 400 when that certificate check was bypassed for diagnosis.
The live cutover has not yet been applied from this workstation: its SSH key
was rejected by both `deploy` and `root`.

## Upload from Windows PowerShell

The supplied ZIP contains only the cutover script, the two new Nginx templates,
and this guide. It contains no environment file, credentials, application release,
database or media. Use the SSH user you normally use for this VPS; the example
below uses the documented `deploy` user.

```powershell
scp "E:\Client\Mehrab\ims\sescco-ims\ms-domain-cutover.zip" deploy@31.70.114.86:/tmp/ms-domain-cutover.zip
ssh deploy@31.70.114.86
```

## Run on the VPS

```bash
cd /opt/sites/ims
sudo python3 -m zipfile -e /tmp/ms-domain-cutover.zip /opt/sites/ims
sudo bash scripts/change-public-domain.sh
```

The script asks for a real email address for the HTTPS certificate if it needs
to issue one. You can provide it in advance:

```bash
sudo bash scripts/change-public-domain.sh --email YOUR_REAL_EMAIL
```

The existing IMS stack must already be running, with `.env.production`, host
Nginx, Certbot and Docker Compose v2 installed. The script checks that IMS still
uses port 8087, that startup migrations are disabled, and that the DNS record
points directly to the VPS. If the script reports an existing explicit
`ms.sescco.com` virtual host in another file, inspect that file and reconcile
the existing route before running it again.

If an older copy of the script stops with `Set RUN_STARTUP_TASKS=0`, back up
the environment and explicitly disable startup tasks before rerunning it:

```bash
cd /opt/sites/ims
sudo install -d -m 700 backups/domain-preflight
sudo install -m 600 .env.production "backups/domain-preflight/environment-$(date -u +%Y%m%dT%H%M%SZ)"
sudo sed -i '/^[[:space:]]*RUN_STARTUP_TASKS[[:space:]]*=/d' .env.production
printf '\nRUN_STARTUP_TASKS=0\n' | sudo tee -a .env.production >/dev/null
sudo bash scripts/change-public-domain.sh
```

This changes only the startup-task setting. The current script accepts an
omitted setting, which already defaults to zero in Compose, and pins the
effective Compose value to zero during both cutover and rollback.

The script:

1. Checks the running IMS services and the public company site.
2. Saves the environment and the new hostname's previous virtual-host state
   in a restricted directory under `/opt/sites/ims/backups/`.
3. Installs an HTTP virtual host for the certificate challenge, requests a
   certificate for `ms.sescco.com`, and enables the final HTTPS virtual host.
4. Changes only these existing environment values:

   ```env
   IMS_PUBLIC_DOMAIN=ms.sescco.com
   DJANGO_ALLOWED_HOSTS=ms.sescco.com,localhost,127.0.0.1
   DJANGO_CSRF_TRUSTED_ORIGINS=https://ms.sescco.com
   ```

5. Recreates only `ims_web` using its existing image and reloads the IMS gateway
   so it resolves the recreated container's address. This briefly interrupts IMS.
6. Verifies public HTTPS readiness, login and a static asset, then checks the
   company site again. HTTPS certificate verification remains enabled.

It does not run migrations, seeding, a build, an image pull, or a database
restart. The new templates use distinct upstream/rate-limit names so an older
IMS virtual host can remain installed without duplicate Nginx definitions.
An older public hostname is not retained in Django's allowed hosts. Users
should sign in at the new address, and previously issued absolute share links
are not rewritten by this hostname-only change.

On a failure after configuration changes begin, the script attempts to restore
the previous environment and virtual host and recreate IMS with those settings.
It prints the backup directory and an exact manual rollback command. Keep that
backup private: it contains the original production secrets. A newly issued
certificate is retained for later retries.

## Verify after success

```bash
curl -I https://ms.sescco.com/login/
curl -fsS https://ms.sescco.com/app/health/ready/
curl -I https://sescco.com/
sudo certbot certificates
sudo systemctl list-timers --all | grep certbot
```

Open `https://ms.sescco.com/login/` and sign in with your existing account.
Confirm the Inventory and Payroll pages load. The script validates the allowed
host and CSRF origin configuration, but account-based login and CSRF form
submission need this browser check. Existing data and accounts remain in place.
