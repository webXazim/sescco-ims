#!/usr/bin/env python3
"""Synchronize only APP_VERSION in the private production environment.

The release VERSION is authoritative. Preserve every secret and unrelated
variable; do not overwrite .env.production from the example template.

Usage:
    python3 scripts/sync-production-app-version.py --check
    sudo python3 scripts/sync-production-app-version.py --apply
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_PATTERN = re.compile(r"\A[0-9]+\.[0-9]+\.[0-9]+(?:[.-][A-Za-z0-9]+)*\Z")
ASSIGNMENT = re.compile(r"^[ \t]*APP_VERSION[ \t]*=", re.MULTILINE)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true", help="Exit nonzero on a mismatch; make no changes")
    action.add_argument("--apply", action="store_true", help="Back up the env file and update APP_VERSION only")
    args = parser.parse_args()

    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError("Packaged VERSION has an unsupported or unsafe format")

    value = os.environ.get("IMS_ENV_FILE") or str(ROOT / ".env.production")
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / value.removeprefix("./")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Production env file is not a regular file: {path}")
    original = path.read_bytes()
    text = original.decode("utf-8")
    if "\x00" in text:
        raise ValueError("Production environment is not a valid text file")
    entries = list(ASSIGNMENT.finditer(text))
    if len(entries) > 1:
        raise ValueError("Multiple APP_VERSION assignments found; resolve duplicates manually")
    if entries:
        start = entries[0].start()
        end = text.find("\n", start)
        if end == -1:
            end = len(text)
        old_line = text[start:end]
        old_value = old_line.split("=", 1)[1].strip().strip("\"'").split(" #", 1)[0].strip()
        new_text = text[:start] + f"APP_VERSION={version}" + text[end:]
    else:
        old_value = "(missing)"
        new_text = text + ("" if text.endswith("\n") or not text else "\n") + f"APP_VERSION={version}\n"
    if old_value == version and new_text == text:
        print(f"APP_VERSION already matches packaged VERSION={version}; no changes needed.")
        return 0
    if args.check:
        print(f"APP_VERSION mismatch: production={old_value}, packaged={version}. Run this command with --apply.", file=sys.stderr)
        return 1

    # The private environment can contain credentials. Backups are always kept
    # in a git-ignored, owner-only directory; never print its contents.
    backup_dir = ROOT / ".secrets" / "env-backups"
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    backup = backup_dir / f"env.production.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.{os.getpid()}.bak"
    with backup.open("xb") as f:
        os.fchmod(f.fileno(), 0o600)
        f.write(original)
    st = path.stat()
    mode = stat.S_IMODE(st.st_mode)
    fd, temp_name = tempfile.mkstemp(prefix=".env-version-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), mode)
            if hasattr(os, "fchown"):
                os.fchown(f.fileno(), st.st_uid, st.st_gid)
            f.write(new_text.encode("utf-8"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    print(f"Synchronized APP_VERSION: {old_value} -> {version} (other values unchanged; protected backup saved).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"APP_VERSION SYNC ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
