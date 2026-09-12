#!/usr/bin/env python3
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[1]

def need(path, text):
    data=(root/path).read_text(encoding='utf-8')
    if text not in data:
        raise SystemExit(f"SINGLE-COMPANY/BRAND ERROR: {path} missing {text!r}")

def forbid(path, text):
    data=(root/path).read_text(encoding='utf-8')
    if text in data:
        raise SystemExit(f"SINGLE-COMPANY/BRAND ERROR: {path} still contains {text!r}")

asset=root/'static/platform/brand-sescco-mark.webp'
if not asset.is_file() or asset.stat().st_size < 1000:
    raise SystemExit('SINGLE-COMPANY/BRAND ERROR: SESCCO brand asset missing or empty')
need('config/settings/base.py', 'SINGLE_COMPANY_MODE = env_bool("SINGLE_COMPANY_MODE", True)')
need('config/settings/base.py', 'APP_NAME = "SESCCO MS"')
need('config/settings/base.py', 'APP_SUBTITLE = "Management System"')
need('apps/accounts/selectors.py', 'if settings.SINGLE_COMPANY_MODE:')
need('apps/accounts/services.py', 'Company switching is disabled in SESCCO MS single-company mode.')
need('apps/core/checks.py', 'platform.E301')
need('templates/partials/platform_switchers.html', '{% if not SINGLE_COMPANY_MODE and ACTIVE_COMPANY %}')
need('templates/partials/platform_switchers.html', '<small>Module</small>')
need('templates/partials/sidebar.html', "platform/brand-sescco-mark.webp")
need('templates/payroll/app.html', "platform/brand-sescco-mark.webp")
need('templates/registration/login.html', 'SESCCO MS')
need('static/payroll/js/app.js', 'document.title = `${title} — SESCCO MS`;')
need('static/payroll/js/app.js', 'accountMenuRoleLabel.textContent = roleDefinition().label;')
forbid('templates/partials/platform_switchers.html', 'Business area')
forbid('templates/partials/platform_switchers.html', 'Business areas')
print('SESCCO MS single-company branding contract verified.')
