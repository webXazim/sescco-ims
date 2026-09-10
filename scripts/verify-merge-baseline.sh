#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_ROOT}"

fail() {
  printf 'MERGE BASELINE ERROR: %s\n' "$*" >&2
  exit 1
}

printf 'Checking immutable IMS migration baseline...\n'
sha256sum -c merge/baseline-migrations.sha256 >/dev/null \
  || fail "An existing IMS migration changed. Add a new migration instead of rewriting history."

if [[ -f merge/frozen-merge-migrations.sha256 ]]; then
  printf 'Checking immutable merge migration history...\n'
  sha256sum -c merge/frozen-merge-migrations.sha256 >/dev/null \
    || fail "A frozen merge migration changed. Add a new migration instead of rewriting merge history."
fi

printf 'Checking authoritative identity/deployment contracts...\n'
grep -Fq 'AUTH_USER_MODEL = "accounts.User"' config/settings/base.py \
  || fail "AUTH_USER_MODEL is no longer the existing IMS accounts.User."
grep -Fq 'apps.internal_payroll.apps.InternalPayrollConfig' config/settings/base.py \
  || fail "Internal Payroll is no longer installed in the merged Django platform."
grep -Fq 'include("apps.internal_payroll.urls")' config/urls.py \
  || fail "The preserved /api/internal Payroll route contract was removed."
grep -Fq 'apps.rental_manpower.apps.RentalManpowerConfig' config/settings/base.py \
  || fail "Rental Manpower is no longer installed in the merged Django platform."
grep -Fq 'include("apps.rental_manpower.urls")' config/urls.py \
  || fail "The preserved /api/rental Payroll route contract was removed."
grep -Fq 'apps.documents.apps.DocumentsConfig' config/settings/base.py \
  || fail "Payroll Documents is no longer installed in the merged Django platform."
grep -Fq 'include("apps.documents.urls")' config/urls.py \
  || fail "The preserved /api/documents/ route contract was removed."
grep -Fq 'apps.core.api_urls' config/urls.py \
  || fail "The preserved management/reports/settings API route contract was removed."
if grep -R -n -E 'class[[:space:]]+RentalProject\b' apps/rental_manpower --include='*.py' --exclude-dir='__pycache__' >/dev/null; then
  fail "A duplicate rental_manpower.RentalProject model was introduced. Use projects.Project."
fi
if grep -R -n -F 'db_table = "rental_project"' apps/rental_manpower --include='*.py' --exclude-dir='__pycache__' >/dev/null; then
  fail "A duplicate rental_project database table was introduced. Use projects.Project."
fi
grep -Eq '^name:[[:space:]]*ims[[:space:]]*$' docker-compose.yml \
  || fail "Docker Compose project identity changed."
grep -Fq 'name: ims_postgres_data' docker-compose.yml \
  || fail "IMS PostgreSQL volume identity changed."
grep -Fq 'name: ims_static_data' docker-compose.yml \
  || fail "IMS static volume identity changed."
grep -Fq 'name: ims_media_data' docker-compose.yml \
  || fail "IMS media volume identity changed."

if command -v python3 >/dev/null 2>&1; then
  printf 'Checking Python source syntax...\n'
  python3 -m compileall -q apps config manage.py
fi

if command -v node >/dev/null 2>&1; then
  node --check static/js/app.js
fi

printf 'Merge baseline verified.\n'
