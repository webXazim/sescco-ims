"""Exercise the real shell workflow with fake Docker/rclone; no live data access.

Run with python scripts/test-backup-workflow.py. Requires Bash and GNU utilities.
On Windows set IMS_TEST_BASH to the Git Bash executable.
The flock stub checks contention handling, not kernel locking semantics.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BASH = os.environ.get("IMS_TEST_BASH", shutil.which("bash") or "bash")


def shell_path(path):
    value = Path(path).resolve().as_posix()
    if os.name == "nt":
        value = "/" + value[0].lower() + value[2:]
    return value


class BackupWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ims-backup-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        (self.root / "VERSION").write_text("test\n")
        (self.root / ".env.production").write_text(
            "PAYROLL_FIELD_ENCRYPTION_KEY=test-key\n"
            "IMS_BACKUP_RETENTION_DAYS=1\nIMS_BACKUP_KEEP_COUNT=2\n"
            "IMS_BACKUP_QUIESCE_WEB=1\n"
            f"IMS_OFFSITE_RCLONE_CONFIG={shell_path(self.root / 'rclone.conf')}\n"
            "IMS_OFFSITE_RCLONE_REMOTE=encrypted:\nIMS_OFFSITE_BACKUP_RETENTION_DAYS=90\n"
            "IMS_OFFSITE_RCLONE_TRANSFERS=3\n"
        )
        (self.root / "rclone.conf").write_text("test fixture; no credentials\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith("IMS_"):
                del self.env[key]
        self.env.update(TEST_ROOT=shell_path(self.root), MOCK_TYPE="crypt")
        self.tool("flock", '[[ "${MOCK_LOCK_FAIL:-0}" != 1 ]]')
        self.tool("docker", r'''
printf '%s\n' "$*" >> "$TEST_ROOT/docker.log"
if [[ "$1" == inspect ]]; then
  [[ "$*" == *".Image"* ]] && { echo sha256:test-postgres; exit; }
  echo healthy; exit
fi
[[ "$1" == create ]] && { echo isolated-test-container; exit; }
if [[ "$1" == exec && "$*" == *"pg_restore"* ]]; then
  cat >/dev/null
  [[ "${MOCK_RESTORE_FAIL:-0}" != 1 ]]
  exit
fi
if [[ "$1" == exec && "$*" == *"psql"* ]]; then
  echo "${MOCK_MIGRATIONS:-42}"; exit
fi
[[ "$*" == *" ps --status running --services"* ]] && { echo ims_web; exit; }
[[ "$*" == *" ps -q "* ]] && { echo test-container; exit; }
if [[ "$*" == *pg_dump* ]]; then
  [[ "${MOCK_DUMP_FAIL:-0}" != 1 ]] || exit 1
  echo fake-pg-dump; exit
fi
[[ "$*" == *pg_restore* ]] && { cat >/dev/null; exit; }
[[ "$*" == *"tar -C"* ]] && { tar -czf - --files-from /dev/null; exit; }
exit 0
''')
        self.tool("git", r'''
[[ "$*" == *"rev-parse HEAD" ]] && { echo abc123; exit; }
if [[ "$*" == *"bundle create"* ]]; then
  while [[ "$1" != create ]]; do shift; done
  echo source > "$2"
fi
exit 0
''')
        self.tool("rclone", r'''
printf '%s\n' "$*" >> "$TEST_ROOT/rclone.log"
case "$3" in
  listremotes) echo "encrypted: ${MOCK_TYPE}" ;;
  copy)
    [[ "${MOCK_COPY_FAIL:-0}" != 1 ]] || exit 1
    if [[ "$*" == *"encrypted:"*".restore-check."* ]]; then
      [[ "${MOCK_DOWNLOAD_FAIL:-0}" != 1 ]] || exit 1
      source_arg="${@: -2:1}"
      target_arg="${@: -1}"
      name="${source_arg#encrypted:}"
      cp -a "$TEST_ROOT/backups/$name/." "$target_arg/"
      [[ "${MOCK_CORRUPT_DOWNLOAD:-0}" != 1 ]] || echo corrupt >> "$target_arg/database.dump"
    fi
    ;;
  cryptcheck) [[ "${MOCK_CHECK_FAIL:-0}" != 1 ]] ;;
  lsf) [[ "${MOCK_LIST_FAIL:-0}" != 1 ]] || exit 1
       printf '%s\n' '20000101T000000Z/' 'notes/' '../escape/' '20990101T000000Z/' ;;
esac
''')

    def tool(self, name, body):
        path = self.bin / name
        path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n", newline="\n")
        path.chmod(0o755)

    def run_script(self, name, success=True):
        command = f'export PATH="{shell_path(self.bin)}:$PATH"; bash "{shell_path(self.root / "scripts" / name)}"'
        result = subprocess.run([BASH, "-c", command], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def old_snapshots(self):
        for year in (2000, 2001, 2002):
            folder = self.root / "backups" / f"{year}0101T000000Z"
            folder.mkdir(parents=True)
            (folder / "manifest.txt").write_text("service=ims\n")
            (folder / "SHA256SUMS").touch()
        (self.root / "backups" / "keep-unrelated").mkdir()

    def log(self, name):
        path = self.root / name
        return path.read_text() if path.exists() else ""

    def test_complete_capture_and_env_retention(self):
        self.old_snapshots()
        result = self.run_script("backup.sh")
        folder = self.root / "backups" / result.stdout.strip().splitlines()[-1].split("/")[-1]
        self.assertTrue((folder / "pulse-private.tar.gz").is_file())
        self.assertFalse(list((self.root / "backups").glob(".partial-*")))
        self.assertFalse((self.root / "backups/20000101T000000Z").exists())
        self.assertTrue((self.root / "backups/20020101T000000Z").exists())
        self.assertTrue((self.root / "backups/keep-unrelated").exists())
        self.assertIn("stop ims_web", self.log("docker.log"))
        self.assertIn("start ims_web", self.log("docker.log"))

    def test_failed_capture_resumes_web_without_pruning(self):
        self.old_snapshots()
        self.env["MOCK_DUMP_FAIL"] = "1"
        self.run_script("backup.sh", success=False)
        self.assertTrue((self.root / "backups/20000101T000000Z").exists())
        self.assertFalse(list((self.root / "backups").glob(".partial-*")))
        self.assertIn("start ims_web", self.log("docker.log"))

    def test_plain_remote_rejected_after_local_capture(self):
        self.env["MOCK_TYPE"] = "drive"
        self.run_script("backup-to-google-drive.sh", success=False)
        self.assertNotIn(" copy ", self.log("rclone.log"))
        self.assertEqual(len(list((self.root / "backups").glob("*/database.dump"))), 1)

    def test_failed_remote_steps_never_report_success(self):
        for failure in ("MOCK_COPY_FAIL", "MOCK_CHECK_FAIL", "MOCK_LIST_FAIL"):
            with self.subTest(failure=failure):
                self.env[failure] = "1"
                self.run_script("backup-to-google-drive.sh", success=False)
                self.assertNotIn(" purge ", self.log("rclone.log"))
                self.assertFalse((self.root / "backups/.last-offsite-success").exists())
                self.assertEqual(len(list((self.root / "backups").glob("*/database.dump"))), 1)
                del self.env[failure]
                shutil.rmtree(self.root / "backups")
                (self.root / "rclone.log").unlink()

    def test_success_upload_prunes_only_timestamp_folders(self):
        self.run_script("backup-to-google-drive.sh")
        log = self.log("rclone.log")
        self.assertIn("--transfers 3", log)
        self.assertIn("purge encrypted:20000101T000000Z", log)
        self.assertNotIn("purge encrypted:notes", log)
        self.assertNotIn("purge encrypted:2099", log)
        self.assertTrue((self.root / "backups/.last-offsite-success").is_file())
        docker_log = self.log("docker.log")
        self.assertIn("--network none", docker_log)
        self.assertNotIn("--volume", next(line for line in docker_log.splitlines() if line.startswith("create ")))
        self.assertIn("--single-transaction --exit-on-error", docker_log)
        self.assertIn("rm --force --volumes isolated-test-container", docker_log)
        self.run_script("check-backup-health.sh")
        (self.root / "backups/.last-offsite-success").write_text("1\n")
        self.run_script("check-backup-health.sh", success=False)

    def test_failed_download_or_restore_never_prunes_or_updates_health(self):
        for failure in ("MOCK_DOWNLOAD_FAIL", "MOCK_CORRUPT_DOWNLOAD", "MOCK_RESTORE_FAIL", "MOCK_MIGRATIONS"):
            with self.subTest(failure=failure):
                self.env[failure] = "0" if failure == "MOCK_MIGRATIONS" else "1"
                self.run_script("backup-to-google-drive.sh", success=False)
                self.assertNotIn(" purge ", self.log("rclone.log"))
                self.assertFalse((self.root / "backups/.last-offsite-success").exists())
                self.assertFalse(list((self.root / "backups").glob(".restore-check.*")))
                if failure in ("MOCK_RESTORE_FAIL", "MOCK_MIGRATIONS"):
                    self.assertIn("rm --force --volumes isolated-test-container", self.log("docker.log"))
                del self.env[failure]
                shutil.rmtree(self.root / "backups")
                (self.root / "rclone.log").unlink()
                (self.root / "docker.log").unlink()

    def test_lock_contention_fails(self):
        self.env["MOCK_LOCK_FAIL"] = "1"
        self.run_script("backup.sh", success=False)
        self.assertNotIn("pg_dump", self.log("docker.log"))


if __name__ == "__main__":
    unittest.main()
