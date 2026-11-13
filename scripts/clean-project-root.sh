#!/usr/bin/env bash
# Remove only the known obsolete root-level release documents once their
# archived copies exist. Preserve server-local differences under .secrets.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f docs/releases/.root-notes.json ]] || { echo 'Missing root-notes archive manifest' >&2; exit 1; }
python3 - "$ROOT" <<'PY'
import json, pathlib, shutil, sys, os, stat
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / 'docs/releases/.root-notes.json').read_text())
backup = root / '.secrets' / 'root-note-backups'
cleaned = 0
preserved = 0
for name, dest in sorted(manifest.items()):
    src = root / name
    archived = root / dest / name
    if not archived.is_file():
        raise SystemExit(f'Required archived document is missing: {archived}')
    if not src.exists():
        continue
    if src.is_symlink() or not src.is_file():
        raise SystemExit(f'Refusing to alter unexpected root entry: {src}')
    if src.read_bytes() != archived.read_bytes():
        backup.mkdir(parents=True,exist_ok=True,mode=0o700)
        os.chmod(backup,0o700)
        target = backup / name
        if target.exists() and target.read_bytes() != src.read_bytes():
            import hashlib
            target = backup / (name + '.' + hashlib.sha256(src.read_bytes()).hexdigest()[:12])
        if not target.exists():
            with target.open('xb') as fp:
                os.fchmod(fp.fileno(),0o600)
                fp.write(src.read_bytes())
        preserved += 1
    src.unlink()
    cleaned += 1
print(f'Project root cleanup: {cleaned} obsolete files relocated; {preserved} different server copies backed up privately.')
print('Kept README.md, RELEASE_NOTES.md, deploy.md, VERSION and all source/config files.')
PY
