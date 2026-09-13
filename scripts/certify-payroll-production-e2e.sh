#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

fail() { printf 'PAYROLL E2E CERTIFICATION ERROR: %s\n' "$*" >&2; exit 1; }
command -v "${PYTHON_BIN}" >/dev/null 2>&1 || fail "${PYTHON_BIN} is required."

printf 'Verifying the frozen Payroll production-E2E certification contract...\n'
"${PYTHON_BIN}" scripts/verify-payroll-production-e2e.py

printf 'Running Django deployment/schema checks...\n'
"${PYTHON_BIN}" manage.py check --deploy --fail-level ERROR
"${PYTHON_BIN}" manage.py makemigrations --check --dry-run

mapfile -t TEST_LABELS < <("${PYTHON_BIN}" - <<'PY'
import json
from pathlib import Path
contract = json.loads(Path('merge/payroll-production-e2e.json').read_text(encoding='utf-8'))
for label in contract['runtime_test_labels']:
    print(label)
PY
)
(( ${#TEST_LABELS[@]} > 0 )) || fail 'No runtime test labels are registered.'

printf 'Running curated Payroll production-E2E Django suite (%s labels)...\n' "${#TEST_LABELS[@]}"
"${PYTHON_BIN}" manage.py test "${TEST_LABELS[@]}" --noinput

printf 'Payroll production-E2E certification passed.\n'
