#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { printf 'inventory explorer UX verification failed: %s\n' "$*" >&2; exit 1; }
require_text() {
  local file="$1" text="$2"
  grep -Fq -- "$text" "$file" || fail "$file is missing: $text"
}

require_text templates/inventory/stockitem_list.html 'class="explorer-toolbar inventory-explorer-toolbar"'
require_text templates/inventory/stockitem_list.html 'class="search-field inventory-explorer-search"'
require_text templates/inventory/stockitem_list.html 'data-condition-filter'
require_text templates/inventory/stockitem_list.html 'class="condition-filter-popover"'
require_text templates/inventory/stockitem_list.html 'inventory-explorer-icon-control'
require_text templates/inventory/stockitem_list.html 'with icon_only="1"'
require_text templates/partials/column_settings.html 'inventory-explorer-icon-control'
require_text templates/inventory/stockitem_list.html '{{ filter_form.condition }}'
require_text static/css/styles.css '.inventory-explorer-toolbar > .inventory-explorer-search'
require_text static/css/styles.css 'flex: 1 1 460px;'
require_text static/css/styles.css 'max-width: none;'
require_text static/css/styles.css '.inventory-explorer-icon-control'
require_text static/css/styles.css '.condition-filter-trigger'
require_text static/css/styles.css 'height: 40px;'
require_text static/css/styles.css '.inventory-explorer-filters #id_location'
require_text static/js/app.js 'const conditionFilter = liveFilterForm.querySelector("[data-condition-filter]");'
require_text static/js/app.js 'input[name="condition"]'
require_text static/js/app.js 'conditionSummary.textContent = "Any condition";'
require_text static/js/app.js 'conditionInputs.forEach((input) => {'
require_text static/js/app.js 'refreshFilterResults();'

if command -v node >/dev/null 2>&1; then
  node --check static/js/app.js
fi

printf 'Inventory Explorer search-first toolbar, icon actions and condition dropdown verified.\n'
