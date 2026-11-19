# Production VPS and Google Drive backup runbook

## What the code does, and what still needs VPS validation

The app uses PostgreSQL 17 and Docker volumes `ims_media_data` and
`ims_pulse_private_data`. `backup.sh` captures all three, Git history (plus tracked
working-tree changes), `.env.production`, a manifest and checksums. Static assets
are rebuilt. Untracked source files, host Nginx/TLS files and host configuration
are not included: deploy committed code and keep host provisioning separately.

The repository already included an rclone uploader and systemd units. The review
found ignored `.env.production` local retention, no capture lock, partially written
directories presented as completed backups, no pre-upload crypt check, file-age
remote deletion, conflicting cron instructions, and no freshness check. These are
addressed in this change. VPS state and Drive access have not been inspected.

## Starting policy

| Item | Production starting point |
| --- | --- |
| Schedule | Daily 02:20 Asia/Riyadh, plus up to 20 minutes jitter |
| Local storage | `./backups`, older than 7 days pruned; at least 7 newest retained |
| Off-site storage | Full encrypted recovery sets for 90 days in a dedicated Drive folder |
| Consistency | Brief maintenance during database and document capture |
| Recovery point objective | Up to 24 hours under normal successful daily operation |
| Recovery time objective | Initially budget 2–4 hours; measure on a fresh-host drill |
| Alert | External missed-success heartbeat at 36 hours; VPS disk warning at 75%, critical at 85% |
| Restore drill | Before enabling automation, then monthly from a downloaded Drive copy |

Every snapshot is a full copy, with no deduplication. If a complete set is S GB,
budget at least 8 × S GB local (seven retained plus one in progress), extra room
for database growth and deployment backups, and roughly 90 × S GB on Drive plus
headroom. Each automated verification also needs a temporary full downloaded set
and enough Docker storage for a restored database including indexes. The restore
container is limited to 512 MB RAM and one CPU; include its disk I/O and full
download in duration/bandwidth planning. Age plus minimum-count retention can retain more than seven snapshots,
especially with frequent deployments. Measure with `du -sh backups/*` and
`df -h .`; adjust to actual growth and available capacity. Drive Trash can continue
using quota after pruning; review its lifecycle and storage usage separately.

This policy needs a larger Drive plan if full sets exceed available quota. Do not
enable an unmeasured 90-day full-copy policy and assume free Drive is sufficient.
For substantially larger datasets, evaluate incremental backup storage rather
than silently reducing restore coverage. For recovery points under 24 hours,
plan more frequent DB backups or PostgreSQL WAL archiving separately.

## 1. Inspect the VPS without changing it

Run as the intended `deploy` account in `/opt/sites/ims`:

```bash
docker compose --env-file .env.production ps
systemctl status ims-backup.timer ims-backup.service --no-pager
systemctl cat ims-backup.service ims-backup.timer
systemctl list-timers --all
crontab -l
sudo crontab -l
sudo ls -l /etc/cron.d
df -h /opt/sites/ims
du -sh backups 2>/dev/null
journalctl -u ims-backup.service -n 100 --no-pager
```

Missing units or crontabs are expected on a new host. Identify any existing cron
entry, root-owned backups, overrides, and the actual project path/service user.
The shipped units assume `deploy` owns the repo and can access Docker. Use the
existing Docker operator account; do not run the whole job as root merely to fix
ownership. Never paste `.env.production`, tokens or rclone config into logs/chat.

## 2. Install and configure rclone

Install a current stable rclone from the [official installation instructions](https://rclone.org/install/)
and the host packages `util-linux` (flock), `git`, `tar`, `coreutils` and `curl`.
Docker Compose v2 must already work. Check `rclone version` and
`rclone listremotes --help` includes `--long`.

Use a dedicated organization-controlled Google account with MFA, recovery details
and adequate quota. Configure a normal Google Drive remote with OAuth, using
[rclone's Drive instructions](https://rclone.org/drive/) and
[headless authorization](https://rclone.org/remote_setup/). A service account is
appropriate only with the required Workspace/Shared Drive configuration; do not
assume it provides storage quota for a personal Drive. If using your own OAuth
client, follow the production consent-screen guidance; a testing-mode client can
lose authorization after seven days.

```bash
cd /opt/sites/ims
install -d -m 700 .secrets backups
umask 077
rclone --config /opt/sites/ims/.secrets/rclone.conf config
chmod 600 .secrets/rclone.conf
```

Create `gdrive` of type `drive`, then `ms-backups` of type `crypt`:

```ini
# Shape only; create real secrets interactively using rclone config.
[gdrive]
type = drive
# OAuth client/token fields are written by rclone.

[ms-backups]
type = crypt
remote = gdrive:SESCCO-IMS-production-backups
filename_encryption = standard
directory_name_encryption = true
# password and password2 are written by rclone.
```

Use strong generated crypt password and salt. This Drive folder must be exclusive
to this IMS installation; the retention job deletes timestamp-named folders there.
Do not configure overlapping backup writers from another VPS.
The `crypt` wrapper encrypts content and names before upload, as described in the
[rclone crypt documentation](https://rclone.org/crypt/).

Keep an independent password-manager recovery record containing the crypt
password/salt, the complete rclone config, Google account recovery access,
`PAYROLL_FIELD_ENCRYPTION_KEY`, and host provisioning/TLS instructions. Rclone's
stored obscured passwords are reversible: treat its config as a secret. The
environment archive alone cannot unlock Drive after losing the VPS. Avoid an
interactive rclone config password unless an unattended secret-loading mechanism
has also been configured and tested as the service user.

## 3. Configure the production environment

Merge these settings into the existing `.env.production`; do not replace its
application secrets. A different absolute backup location is supported, but it
must be owned by the service user and match the Compose backup bind mount.

```dotenv
IMS_BACKUP_DIR=./backups
IMS_BACKUP_RETENTION_DAYS=7
IMS_BACKUP_KEEP_COUNT=7
IMS_BACKUP_QUIESCE_WEB=1
IMS_OFFSITE_RCLONE_CONFIG=/opt/sites/ims/.secrets/rclone.conf
IMS_OFFSITE_RCLONE_REMOTE=ms-backups:
IMS_OFFSITE_RCLONE_TRANSFERS=2
IMS_OFFSITE_BACKUP_RETENTION_DAYS=90
IMS_BACKUP_MAX_AGE_HOURS=36
```

Quiescing gracefully stops a running `ims_web`, copies the DB and files, then
restarts it before uploading. Users will briefly get gateway errors. Rehearse and
measure the outage and choose an agreed maintenance window. Stop other writers
if any have been added outside Compose. `IMS_BACKUP_QUIESCE_WEB=0` stays online
but does not guarantee a matched database/files snapshot. The script default is
0 for compatibility; the production example explicitly selects 1.

Local recovery sets contain sensitive database data and plaintext environment
secrets, with directories 700 and files 600. They are encrypted only on Drive.

## 4. Manual acceptance as the service user

```bash
cd /opt/sites/ims
bash scripts/backup-to-google-drive.sh
bash scripts/check-backup-health.sh
rclone --config .secrets/rclone.conf lsf ms-backups: --dirs-only
```

Choose the timestamp printed by the job, and replace `TIMESTAMP` below. Download
into the configured backup root so the production restore bind mount can read it.
On this existing host, use a separate directory named `download-test`:

```bash
install -d -m 700 backups/download-test
rclone --config .secrets/rclone.conf copy ms-backups:TIMESTAMP backups/download-test
chmod -R go-rwx backups/download-test
bash scripts/verify-backup.sh backups/download-test --require-recovery-bundle
```

`cryptcheck` verifies ciphertext against the local source using the underlying
Drive checksums; see the [official verification behavior](https://rclone.org/commands/rclone_cryptcheck/).
Every automated job additionally downloads the uploaded set, verifies its checksums
and all archives, restores the full dump with `pg_restore --single-transaction
--exit-on-error` in a disposable PostgreSQL container, and queries its Django
migration history. It uses the exact installed production database image, with no
production volumes/credentials attached and no network or published ports. The
container and its anonymous volume are removed on success or ordinary failure.
These checks prove database restore execution and file archive integrity, while
application behavior still requires the periodic drill below. On staging/a separate host,
run `scripts/rehearse-production-freeze.sh` on this downloaded copy to test the
database/migrations/application. That existing rehearsal is resource intensive and
does not restore the private Pulse evidence archive: additionally restore the
downloaded set using `restore.sh` on a **separate test deployment**, verify private
receipts and representative documents through the application, and record timings
and row counts. Never run destructive restore acceptance against production.
Remove the manually managed `download-test` after acceptance; retention ignores it.

Test a failed upload on staging too: the local set should remain, the job should
fail, remote pruning should not run, and no fresh success marker should appear.

## 5. Enable the single daily schedule

Remove the identified old IMS backup cron entry using `crontab -e` or
`sudo crontab -e`, leaving unrelated entries intact. Adapt the supplied service
paths/user if your deployment differs. Install the units:

```bash
sudo install -m 644 deploy/systemd/ims-backup.service /etc/systemd/system/ims-backup.service
sudo install -m 644 deploy/systemd/ims-backup.timer /etc/systemd/system/ims-backup.timer
sudo systemctl daemon-reload
sudo systemctl start ims-backup.service
sudo systemctl enable --now ims-backup.timer
systemctl list-timers ims-backup.timer
journalctl -u ims-backup.service -n 100 --no-pager
```

`Persistent=true` runs one missed backup after the host comes back. The job has a
two-hour limit; increase it only after measuring snapshot/upload duration. Locks
reject overlapping captures/uploads instead of treating a skipped run as success.
Do not deploy or restore during the scheduled capture/upload window. Local
pruning operates after a verified capture even if Drive later fails, keeping the
VPS from accumulating unlimited failed-upload sets. Upload failures are not
automatically backfilled; the next run uploads a fresh snapshot.

## 6. Make failures visible

Systemd failure logs alone do not notify anyone. Configure an external dead-man
heartbeat with a 36-hour missed-success alert to the responsible operator before
relying on automation. An external service also detects a dead VPS or disabled
timer. With your existing monitoring provider, a successful-job hook can be a
systemd drop-in from `sudo systemctl edit ims-backup.service`:

```ini
[Service]
# Replace with the private success URL supplied by your monitoring provider.
ExecStartPost=/usr/bin/curl --fail --silent --show-error --retry 3 --max-time 30 https://YOUR-MONITOR/YOUR-PRIVATE-SUCCESS-URL
```

Reload systemd and test the hook as well as a deliberately missed heartbeat.
Do not commit that private URL. Alternatively, have an external monitoring agent
run `bash /opt/sites/ims/scripts/check-backup-health.sh` every 15 minutes and alert
on nonzero exit **and** host/probe unavailability. It checks the timestamp written
only after a successful upload, cryptcheck, full downloaded-copy verification,
isolated database restore/query and pruning pass. Old pre-restore-test success
markers are rejected until a new job completes. Add disk and Drive
quota alerts in the same monitoring system. Assign a primary and backup operator.

On failure, inspect the journal, disk space, Drive quota and OAuth validity. If a
capture was killed hard, check `ims_web` is running and restart it if needed.
SIGKILL/host crashes can leave hidden `.partial-*` directories; inspect and remove
only confirmed abandoned partial directories while no backup is running. A hard
kill can also leave a `.restore-check.*` download directory or a restore-test
container. Inspect `docker ps -a --filter label=ims.backup-restore-test=true` and
remove only a confirmed abandoned test container by its exact ID with
`docker rm --force --volumes CONTAINER_ID`; never prune production volumes.

## 7. Disaster recovery and monthly drill

1. Recover the independent rclone configuration/crypt secrets onto a clean host
   with protected permissions. Install Docker Compose, Git, tar and rclone.
2. List the crypt remote, choose a known-good UTC timestamp, and download it to a
   protected recovery directory. Run `sha256sum --check SHA256SUMS` there.
3. Clone `source.bundle` into `/opt/sites/ims`, check out `source_revision` from
   the manifest, and apply `source-working-tree.patch` if present. Restore
   `production-config.tar.gz` there with umask 077; protect `.env.production` as
   mode 600. Confirm the Payroll key matches the manifest fingerprint. Recover
   missing host proxy/TLS configuration from the separate provisioning record.
4. Place the selected recovery directory inside the configured `IMS_BACKUP_DIR`.
   On a fresh disaster-recovery host only, use
   `IMS_SKIP_SAFETY_BACKUP=1 bash scripts/restore.sh backups/TIMESTAMP --confirm`.
   For an existing deployment leave the safety backup enabled. The restore
   script rebuilds the app, replaces its data volumes and runs release tasks.
5. Verify database counts, login, permissions, payroll decryption, private receipts,
   document downloads and application health before routing live traffic. Record
   the recovery point, duration and any missing infrastructure instructions.

Keep the evidence from each monthly drill outside the failed host. Google Drive
with VPS-held delete credentials is not immutable storage; maintain an occasional
independent offline recovery copy for protection against account/host compromise.
